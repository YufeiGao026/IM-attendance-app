import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import random
from sqlalchemy import text, create_engine, exc
import time
from functools import wraps
import logging
import calendar

# ========== 页面配置 ==========
st.set_page_config(page_title="仓库出勤统计", layout="wide")

# ========== 日志配置 ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== 硬编码配置（请修改以下内容） ==========
# 数据库连接信息（替换为您的实际信息）
DB_HOST = "gateway01.us-east-1.prod.aws.tidbcloud.com"          # 例如：127.0.0.1
DB_PORT = 4000
DB_USER = "3CPzLRo7kXD4JE5.root"
DB_PASSWORD = "jdJwdm2QejFDajX4"
DB_NAME = "attendance_db"

# 登录凭据
VALID_USERNAME = "Ivy_Gao"
VALID_PASSWORD = "IM_AttendanceData_2606"
ADMIN_USERS = ["Ivy_Gao"]
ALLOWED_USERS = ["Ivy_Gao", "Tiffany"]

# ========== 标准列名 ==========
STANDARD_COLS = ["区域", "仓库名称", "日期", "供应商", "班次", "长期工_日结工", "人数"]
PRICE_CARD_COLS = ["区域", "仓库名称", "供应商", "班次", "长期工_日结工", "周日_非周日", "单价", "生效时间", "失效时间"]
OPS_COLS = ["biz_date", "station_code", "station_name", "class_name", "is_conso", "volume"]

# ========== 区域映射（用于模拟数据） ==========
REGION_MAPPING = {
    "CDC SP": "东南区", "CDC RJ": "南区", "CDC MG": "北区",
    "TP BAR": "FM", "TP IMN": "FM", "TP IMG": "FM",
    "PA GUA": "东南区", "Drop BRA": "南区", "GLP Guarulhos": "东南区",
}

# ========== 数据库引擎单例（硬编码连接信息） ==========
@st.cache_resource
def init_db_engine():
    """初始化数据库引擎（单例），使用硬编码配置"""
    try:
        url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=280,
            pool_size=5,
            max_overflow=10,
            connect_args={'connect_timeout': 30}
        )
        return engine
    except Exception as e:
        st.error(f"数据库引擎初始化失败: {e}")
        raise

def get_db_connection():
    """获取数据库连接"""
    engine = init_db_engine()
    return engine.connect()

# ========== 重试装饰器 ==========
def retry_on_db_error(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "2013" in str(e) or "Lost connection" in str(e):
                        if attempt < max_retries - 1:
                            st.warning(f"数据库连接超时，正在重试 ({attempt+1}/{max_retries})...")
                            time.sleep(delay)
                            st.cache_resource.clear()  # 强制重建引擎
                            continue
                        else:
                            logger.error(f"重试{max_retries}次后仍失败: {e}")
                            raise
                    else:
                        logger.error(f"数据库错误: {e}")
                        raise
            return None
        return wrapper
    return decorator

# ========== 数据加载函数（优化版） ==========

def get_latest_attendance(user=None):
    """
    获取每个仓库+年月的最新版本数据（支持用户过滤）
    使用 JOIN 子查询，返回该版本的所有记录
    """
    engine = init_db_engine()
    with engine.connect() as conn:
        query = """
        WITH max_version AS (
            SELECT 仓库名称, DATE_FORMAT(日期, '%Y-%m') AS ym, MAX(版本号) AS max_v
            FROM attendance
            WHERE 1=1
        """
        params = {}
        if user and user not in ADMIN_USERS:
            query += " AND 上传人 = :user"
            params['user'] = user
        query += """
            GROUP BY 仓库名称, ym
        )
        SELECT a.*
        FROM attendance a
        JOIN max_version m 
            ON a.仓库名称 = m.仓库名称 
            AND DATE_FORMAT(a.日期, '%Y-%m') = m.ym 
            AND a.版本号 = m.max_v
        ORDER BY a.日期 DESC, a.仓库名称
        """
        df = pd.read_sql(text(query), conn, params=params)
        return df

def get_operation_data():
    """获取所有操作量数据"""
    engine = init_db_engine()
    with engine.connect() as conn:
        query = """
        SELECT 
            station_name AS 仓库名称,
            biz_date AS 日期,
            class_name AS 班次,
            volume AS 操作量
        FROM operations
        """
        df = pd.read_sql(text(query), conn)
        if "日期" in df.columns:
            df["日期"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
        return df

def get_price_card_data(version=None):
    """获取价卡数据，若未指定版本则返回最新上传的一版（按上传时间取最新）"""
    engine = init_db_engine()
    with engine.connect() as conn:
        if version:
            query = "SELECT * FROM price_card WHERE 版本号 = :version"
            df = pd.read_sql(text(query), conn, params={"version": version})
        else:
            # 关键改动：获取上传时间最新的那个版本的所有记录
            query = """
                SELECT * FROM price_card 
                WHERE 上传时间 = (SELECT MAX(上传时间) FROM price_card)
            """
            df = pd.read_sql(text(query), conn)
        return df
# ========== 数据写入函数（带重试） ==========
@retry_on_db_error(max_retries=3)
def save_attendance_to_db(df):
    engine = init_db_engine()
    with engine.begin() as conn:
        df.to_sql("attendance", conn, if_exists="append", index=False)
    return len(df), 0

@retry_on_db_error(max_retries=3)
def save_operations_to_db(df):
    engine = init_db_engine()
    with engine.begin() as conn:
        for _, row in df.iterrows():
            sql = text("""
                INSERT INTO operations (biz_date, station_code, station_name, class_name, is_conso, volume, 上传人, 上传时间, 版本号)
                VALUES (:biz_date, :station_code, :station_name, :class_name, :is_conso, :volume, :上传人, :上传时间, :版本号)
                ON DUPLICATE KEY UPDATE
                    station_code = VALUES(station_code),
                    is_conso = VALUES(is_conso),
                    volume = VALUES(volume),
                    上传人 = VALUES(上传人),
                    上传时间 = VALUES(上传时间),
                    版本号 = VALUES(版本号)
            """)
            conn.execute(sql, row.to_dict())
    return len(df), 0

@retry_on_db_error(max_retries=3)
def save_price_card_to_db(df):
    engine = init_db_engine()
    with engine.begin() as conn:
        df.to_sql("price_card", conn, if_exists="append", index=False)
    return len(df), 0

# ========== 业务逻辑函数 ==========
def calculate_cost(price_df, date, warehouse, shift, worker_type, is_sunday_or_holiday, supplier):
    """
    根据价卡表计算单价，严格匹配：仓库、班次、人员类型、周日/节假日、供应商，且在生效期内
    """
    date_obj = pd.to_datetime(date)
    filtered = price_df[
        (price_df["仓库名称"] == warehouse) &
        (price_df["班次"] == shift) &
        (price_df["长期工_日结工"] == worker_type) &
        (price_df["周日_非周日"] == ("周日" if is_sunday_or_holiday else "非周日")) &
        (price_df["供应商"] == supplier) &
        (date_obj >= pd.to_datetime(price_df["生效时间"])) &
        (date_obj <= pd.to_datetime(price_df["失效时间"]))
    ]
    if not filtered.empty:
        return filtered.iloc[0]["单价"]
    else:
        # 静默使用默认单价（不再弹出提醒）
        default = 180.0 if worker_type == "长期工" else 154.0
        return default

def get_work_days_for_month(ym_str):
    """
    输入 'YYYY-MM'，返回该月的工作日数 = 自然天数 - 周日数
    """
    year, month = map(int, ym_str.split('-'))
    _, num_days = calendar.monthrange(year, month)
    # 统计周日数（周一=0, 周日=6）
    sundays = sum(1 for day in range(1, num_days+1) 
                  if datetime(year, month, day).weekday() == 6)
    return num_days - sundays

def generate_efficiency_data(month=None, region=None, warehouse=None):
    """
    返回合并后的出勤+操作量数据（数据库端JOIN），包含人效计算
    """
    engine = init_db_engine()
    with engine.connect() as conn:
        query = """
        WITH latest_att AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY 仓库名称, DATE_FORMAT(日期, '%Y-%m')
                       ORDER BY 版本号 DESC
                   ) AS rn
            FROM attendance
        ),
        filtered_att AS (
            SELECT * FROM latest_att WHERE rn = 1
        )
        SELECT 
            a.区域, a.仓库名称, a.日期, a.供应商, a.班次, a.长期工_日结工, a.人数,
            COALESCE(o.volume, 0) AS 操作量,
            CASE WHEN a.人数 > 0 THEN COALESCE(o.volume, 0) / a.人数 ELSE 0 END AS 人效,
            DATE_FORMAT(a.日期, '%Y-%m') AS 年月
        FROM filtered_att a
        LEFT JOIN operations o 
            ON o.station_name = a.仓库名称 
            AND o.biz_date = a.日期 
            AND o.class_name = a.班次
        WHERE 1=1
        """
        params = {}
        if month and month != "全部":
            query += " AND DATE_FORMAT(a.日期, '%Y-%m') = :month"
            params['month'] = month
        if region and region != "全部":
            query += " AND a.区域 = :region"
            params['region'] = region
        if warehouse and warehouse != "全部":
            query += " AND a.仓库名称 = :warehouse"
            params['warehouse'] = warehouse
        
        df = pd.read_sql(text(query), conn, params=params)
        return df

# ========== 辅助函数 ==========
def generate_version(warehouse, work_date):
    """生成版本号：基于年月最大序号"""
    engine = init_db_engine()
    with engine.connect() as conn:
        month_str = work_date[:7]
        query = """
        SELECT MAX(版本号) as max_version FROM attendance 
        WHERE 仓库名称 = :warehouse AND DATE_FORMAT(日期, '%Y-%m') = :month
        """
        result = conn.execute(text(query), {"warehouse": warehouse, "month": month_str}).fetchone()
        if result and result[0]:
            max_v = result[0]
            # 提取序号部分 V 后面的数字
            try:
                seq = int(max_v.split("V")[1])
                new_seq = seq + 1
            except:
                new_seq = 1
        else:
            new_seq = 1
        date_str = work_date.replace("-", "")
        return f"{date_str}V{new_seq}"

def get_mock_operation_data():
    """模拟操作量数据（仅当数据库无数据时展示）"""
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(60)]
    warehouses = ["CDC SP", "CDC RJ", "CDC MG", "TP BAR", "TP IMN", "TP IMG", "PA GUA", "Drop BRA", "GLP Guarulhos"]
    data = []
    for wh in warehouses:
        for d in dates:
            volume = random.randint(500, 3500)
            data.append({"仓库名称": wh, "日期": d, "操作量": volume})
    return pd.DataFrame(data)

# ========== 验证函数 ==========
def validate_attendance_data(df):
    errors = []
    # 检查必填列
    required = STANDARD_COLS
    if list(df.columns) != required:
        errors.append(f"列名不匹配，期望: {required}，实际: {list(df.columns)}")
        return errors
    # 日期校验
    try:
        pd.to_datetime(df["日期"])
    except:
        errors.append("日期列格式不正确，请使用 YYYY-MM-DD")
    # 人数正整数
    if not df["人数"].apply(lambda x: isinstance(x, (int, float)) and x >= 0).all():
        errors.append("人数必须为非负整数（可以为0）")
    return errors

# ========== Session State 初始化 ==========
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "db_connected" not in st.session_state:
    st.session_state.db_connected = False

# ========== 登录界面 ==========
if not st.session_state.logged_in:
    st.title("🔐 登录")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        if st.button("登录", use_container_width=True):
            if username == VALID_USERNAME and password == VALID_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.rerun()
            else:
                st.error("❌ 用户名或密码错误")
    st.stop()

user = st.session_state.user
is_admin = user in ADMIN_USERS

# ========== 主界面 ==========
current_month = datetime.now().strftime("%Y年%m月")
tab_names = ["📤 上传出勤数据", "📊 数据总览", "📈 外劳人效分析看板", "📊 上传操作量", "💰 价卡配置"]
tabs = st.tabs(tab_names)
tab_dict = {name: tabs[i] for i, name in enumerate(tab_names)}

# ===================== Tab 上传出勤数据 =====================
with tab_dict["📤 上传出勤数据"]:
    st.title("📤 上传出勤数据")
    st.markdown("""
    ### 操作说明
    1. 选择 **仓库、年月、班次、人员类型**。
    2. 点击 **“生成表格”**，系统会生成该月每天、每个供应商的填写表格。
    3. 在对应日期和供应商交叉的格子中填写出勤人数。
    4. 填写完毕后，点击 **“提交数据”**。
    """)

    # ------------------ 加载数据 ------------------
    try:
        df_existing = get_latest_attendance(user if not is_admin else None)
        all_warehouses = sorted(df_existing["仓库名称"].unique()) if not df_existing.empty else []
    except:
        all_warehouses = []

    # 如果数据库中没有仓库，使用预定义列表
    if not all_warehouses:
        all_warehouses = ["CDC SP", "CDC RJ", "CDC MG", "TP BAR", "TP IMN", "TP IMG", "PA GUA", "Drop BRA", "GLP Guarulhos"]

    REGION_MAPPING = {
        "CDC SP": "东南区", "CDC RJ": "南区", "CDC MG": "北区",
        "TP BAR": "FM", "TP IMN": "FM", "TP IMG": "FM",
        "PA GUA": "东南区", "Drop BRA": "南区", "GLP Guarulhos": "东南区",
    }

    # ------------------ 用户选择条件 ------------------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        selected_warehouse = st.selectbox("🏭 仓库", all_warehouses)
    with col2:
        selected_month = st.date_input("📅 年月", value=datetime.now().replace(day=1), format="YYYY-MM")
        month_str = selected_month.strftime("%Y-%m")
    with col3:
        selected_shift = st.selectbox("🕒 班次", ["T1", "T2", "T3"])
    with col4:
        selected_worker_type = st.selectbox("👷 人员类型", ["长期工", "日结工"])

    selected_region = REGION_MAPPING.get(selected_warehouse, "东南区")

    # ------------------ 获取供应商列表（从价卡表） ------------------
    @st.cache_data(ttl=600)
    def get_suppliers_for_warehouse(warehouse):
        try:
            price_df = get_price_card_data()
            if price_df.empty:
                return ["Enfok", "BLITZ", "T2", "T3"]
            suppliers = price_df[price_df["仓库名称"] == warehouse]["供应商"].unique()
            if len(suppliers) == 0:
                return ["Enfok", "BLITZ", "T2", "T3"]
            return sorted(suppliers)
        except:
            return ["Enfok", "BLITZ", "T2", "T3"]

    supplier_list = get_suppliers_for_warehouse(selected_warehouse)

    # ------------------ 生成表格按钮 ------------------
    if st.button("📋 生成表格", use_container_width=True):
        year, month = int(month_str.split("-")[0]), int(month_str.split("-")[1])
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year+1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month+1, 1) - timedelta(days=1)
        date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [d.strftime("%Y-%m-%d") for d in date_list]

        df_template = pd.DataFrame(index=date_strs, columns=supplier_list)
        df_template.index.name = "日期"
        df_template = df_template.fillna(0)

        st.session_state["attendance_wide_df"] = df_template
        st.session_state["attendance_wide_selected"] = {
            "warehouse": selected_warehouse,
            "region": selected_region,
            "shift": selected_shift,
            "worker_type": selected_worker_type,
            "month": month_str
        }

    # ------------------ 如果已生成表格，显示可编辑表格 ------------------
    if "attendance_wide_df" in st.session_state:
        df_wide = st.session_state["attendance_wide_df"]
        st.subheader(f"📋 {st.session_state['attendance_wide_selected']['warehouse']} - {st.session_state['attendance_wide_selected']['month']} 出勤数据")

        edited_df = st.data_editor(
            df_wide,
            column_config={
                col: st.column_config.NumberColumn(col, min_value=0, step=1, default=0)
                for col in df_wide.columns
            },
            use_container_width=True,
            key="attendance_wide_editor"
        )

        # 更新 session_state
        st.session_state["attendance_wide_df"] = edited_df

        # 提交按钮
        col_submit, col_clear = st.columns([2, 1])
        with col_submit:
            if st.button("📤 提交数据", type="primary", use_container_width=True):
                # 检查是否有有效数据
                if edited_df.eq(0).all().all():
                    st.warning("⚠️ 所有数值均为0，没有需要提交的数据")
                else:
                    records = []
                    for date_str in edited_df.index:
                        for supplier in edited_df.columns:
                            val = edited_df.loc[date_str, supplier]
                            if val and val > 0:
                                records.append({
                                    "区域": st.session_state["attendance_wide_selected"]["region"],
                                    "仓库名称": st.session_state["attendance_wide_selected"]["warehouse"],
                                    "日期": date_str,
                                    "供应商": supplier,
                                    "班次": st.session_state["attendance_wide_selected"]["shift"],
                                    "长期工_日结工": st.session_state["attendance_wide_selected"]["worker_type"],
                                    "人数": int(val)
                                })
                    if not records:
                        st.warning("⚠️ 没有找到有效数据（大于0）")
                    else:
                        df_to_submit = pd.DataFrame(records)
                        today = datetime.now().strftime("%Y-%m-%d")
                        version = generate_version(selected_warehouse, today)
                        df_to_submit["上传人"] = user
                        df_to_submit["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df_to_submit["版本号"] = version

                        try:
                            success_count, fail_count = save_attendance_to_db(df_to_submit)
                            if fail_count == 0:
                                st.success(f"✅ 全部 {success_count} 条数据上传成功！版本号：{version}")
                                st.balloons()
                                # 清空表格（重置为空 DataFrame，保留列结构）
                                st.session_state["attendance_wide_df"] = pd.DataFrame(
                                    index=edited_df.index,
                                    columns=edited_df.columns
                                ).fillna(0)
                                # 保留 selected 信息不变，以便继续填写
                            else:
                                st.error(f"❌ 上传失败 {fail_count} 条，请检查数据后重试")
                        except Exception as e:
                            st.error(f"❌ 上传出错：{e}")

        with col_clear:
            if st.button("🗑️ 清空表格", use_container_width=True):
                # 重置为空表格（保留列结构）
                if "attendance_wide_df" in st.session_state:
                    st.session_state["attendance_wide_df"] = pd.DataFrame(
                        index=st.session_state["attendance_wide_df"].index,
                        columns=st.session_state["attendance_wide_df"].columns
                    ).fillna(0)

    else:
        st.info("👆 请先选择条件并点击“生成表格”")

    # ------------------ 模板下载（辅助） ------------------
    st.divider()
    st.caption("💡 也可下载 Excel 模板，在本地填写后复制粘贴到表格中")
    sample_suppliers = get_suppliers_for_warehouse(selected_warehouse)
    if sample_suppliers:
        sample_df = pd.DataFrame(columns=["日期"] + sample_suppliers)
        sample_df.loc[0] = [datetime.now().strftime("%Y-%m-%d")] + [0]*len(sample_suppliers)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            sample_df.to_excel(writer, index=False, sheet_name="出勤数据")
        template_bytes = output.getvalue()
        st.download_button(
            label="📥 下载模板 (Excel)",
            data=template_bytes,
            file_name=f"出勤模板_{selected_warehouse}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

# ===================== Tab 数据总览 =====================
with tab_dict["📊 数据总览"]:
    st.title("📊 数据总览")
    st.caption("仅展示每个仓库每月最新版本的数据，可通过筛选查看特定时间和站点")
    
    df_raw = get_latest_attendance(user if not is_admin else None)
    if len(df_raw) == 0:
        st.info("📭 暂无数据，请先上传")
    else:
        df_raw["年月"] = pd.to_datetime(df_raw["日期"]).dt.strftime("%Y-%m")
        available_months = sorted(df_raw["年月"].unique(), reverse=True)
        available_sites = sorted(df_raw["仓库名称"].unique())
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            selected_month = st.selectbox("📅 选择年月", ["全部"] + available_months, key="overview_month")
        with col_f2:
            selected_site = st.selectbox("🏢 选择站点", ["全部"] + available_sites, key="overview_site")
        
        df_filtered = df_raw.copy()
        if selected_month != "全部":
            df_filtered = df_filtered[df_filtered["年月"] == selected_month]
        if selected_site != "全部":
            df_filtered = df_filtered[df_filtered["仓库名称"] == selected_site]
        
        total_records = len(df_filtered)
        total_people = int(df_filtered["人数"].sum()) if total_records > 0 else 0
        total_warehouses = df_filtered["仓库名称"].nunique()
        total_uploaders = df_filtered["上传人"].nunique()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🏢 仓库数", total_warehouses)
        col2.metric("👷 总外劳人数", total_people)
        col3.metric("📋 总记录数", total_records)
        col4.metric("👤 上传人数", total_uploaders)
        
        st.divider()
        st.dataframe(df_filtered, use_container_width=True)
        
        st.subheader("🏢 各仓库汇总")
        warehouse_summary = df_filtered.groupby("仓库名称").agg({
            "人数": "sum",
            "区域": "first"
        }).reset_index()
        warehouse_summary.columns = ["仓库名称", "总人数", "区域"]
        st.dataframe(warehouse_summary, use_container_width=True)
        
        st.subheader("📥 导出数据")
        csv = df_filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 导出当前数据 (CSV)",
            data=csv,
            file_name=f"仓库出勤汇总_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ===================== Tab 外劳人效分析看板 =====================
with tab_dict["📈 外劳人效分析看板"]:
    st.title("📈 外劳人效分析看板")
    st.caption("核心指标：人效、日均操作量、日均出勤人数、总出勤人天、单人天成本")
    
    st.markdown("""
    <style>
    div[data-testid="metric-container"] .stMetricValue {
        font-size: 28px !important;
    }
    div[data-testid="metric-container"] .stMetricLabel {
        font-size: 14px !important;
    }
    div[data-testid="metric-container"] .stMetricDelta {
        font-size: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 获取真实数据（不再使用模拟数据）
    try:
        merged = generate_efficiency_data()
        if len(merged) == 0:
            st.info("📭 当前无数据，请先上传出勤数据和操作量数据")
            st.stop()
    except Exception as e:
        st.error(f"❌ 读取数据失败：{e}")
        st.stop()
    
    # 筛选条件
    available_months = sorted(merged["年月"].unique(), reverse=True)
    month_options = ["全部"] + available_months
    
    st.subheader("🔍 筛选条件")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        selected_month = st.selectbox("年月", month_options, key="efficiency_month")
    with col_f2:
        regions = sorted(merged["区域"].unique())
        selected_region = st.selectbox("国家/区域", ["全部"] + list(regions), key="efficiency_region")
    with col_f3:
        if selected_region == "全部":
            filtered_warehouses = sorted(merged["仓库名称"].unique())
        else:
            filtered_warehouses = sorted(merged[merged["区域"] == selected_region]["仓库名称"].unique())
        selected_warehouse = st.selectbox("站点", ["全部"] + list(filtered_warehouses), key="efficiency_site")
    
    # 应用筛选
    filtered_df = merged.copy()
    if selected_month != "全部":
        filtered_df = filtered_df[filtered_df["年月"] == selected_month]
    if selected_region != "全部":
        filtered_df = filtered_df[filtered_df["区域"] == selected_region]
    if selected_warehouse != "全部":
        filtered_df = filtered_df[filtered_df["仓库名称"] == selected_warehouse]
    
    if len(filtered_df) == 0:
        st.warning("该筛选条件下无数据")
        st.stop()
    
    # 加载价卡（最新版本）
    price_df = get_price_card_data()
    
    # =============================================================
    # 1. 计算总体指标（基于实际有数据的天数）
    # =============================================================
    # 实际有出勤的天数（按日期去重）
    actual_days = filtered_df["日期"].nunique()
    
    total_volume = int(filtered_df["操作量"].sum())
    total_person_days = filtered_df.groupby("日期")["人数"].sum().sum()
    avg_efficiency = filtered_df["人效"].mean() if len(filtered_df) > 0 else 0
    
    # 日均 = 总量 / 实际天数
    daily_volume = total_volume / actual_days if actual_days > 0 else 0
    daily_headcount = total_person_days / actual_days if actual_days > 0 else 0
    
    # 总成本计算（逐行匹配价卡，静默使用默认单价）
    total_cost = 0.0
    for _, row in filtered_df.iterrows():
        date_obj = pd.to_datetime(row["日期"])
        is_sunday_or_holiday = (date_obj.weekday() == 6) or (date_obj.month == 5 and date_obj.day == 1)
        unit_price = calculate_cost(
            price_df,
            row["日期"],
            row["仓库名称"],
            row["班次"],
            row["长期工_日结工"],
            is_sunday_or_holiday,
            row["供应商"]
        )
        total_cost += unit_price * row["人数"]
    
    unit_cost = total_cost / total_person_days if total_person_days > 0 else 0
    
    # 显示总体指标卡片
    st.subheader("📊 核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("人效", f"{avg_efficiency:.0f}")
    col2.metric("日均操作量", f"{daily_volume:,.0f}")
    col3.metric("日均出勤人数", f"{daily_headcount:.0f}")
    col4.metric("总出勤人天", f"{total_person_days:,.0f}")
    col5.metric("单人天成本", f"R${unit_cost:.2f}")
    st.caption("📌 人效单位：票/人/天 | 日均操作量单位：票 | 日均出勤人数单位：人 | 总出勤人天单位：人天 | 单人天成本单位：R$")
    
    # =============================================================
    # 2. 各站点汇总（同样基于各站点的实际天数）
    # =============================================================
    st.subheader("📋 各站点汇总")
    stations = filtered_df["仓库名称"].unique()
    summary_rows = []
    for station in stations:
        station_df = filtered_df[filtered_df["仓库名称"] == station]
        region = station_df["区域"].iloc[0]
        
        # 该站点的实际有数据天数
        station_days = station_df["日期"].nunique()
        
        vol = station_df["操作量"].sum()
        eff = station_df["人效"].mean()
        person_days = station_df.groupby("日期")["人数"].sum().sum()
        
        daily_vol_station = vol / station_days if station_days > 0 else 0
        daily_headcount_station = person_days / station_days if station_days > 0 else 0
        
        # 成本计算（逐行）
        cost_station = 0.0
        for _, row in station_df.iterrows():
            date_obj = pd.to_datetime(row["日期"])
            is_sunday_or_holiday = (date_obj.weekday() == 6) or (date_obj.month == 5 and date_obj.day == 1)
            unit_price = calculate_cost(
                price_df,
                row["日期"],
                row["仓库名称"],
                row["班次"],
                row["长期工_日结工"],
                is_sunday_or_holiday,
                row["供应商"]
            )
            cost_station += unit_price * row["人数"]
        unit_cost_station = cost_station / person_days if person_days > 0 else 0
        
        summary_rows.append({
            "区域": region,
            "站点": station,
            "人效": f"{eff:.0f}",
            "日均操作量": f"{daily_vol_station:.0f}",
            "日均出勤人数": f"{daily_headcount_station:.0f}",
            "总出勤人天": f"{person_days:,.0f}",
            "单人天成本": f"R${unit_cost_station:.2f}"
        })
    
    result_df = pd.DataFrame(summary_rows)
    st.dataframe(result_df, use_container_width=True)
    
    # 导出
    st.subheader("📥 导出数据")
    csv = result_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 导出当前汇总 (CSV)",
        data=csv,
        file_name=f"外劳人效分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# ===================== Tab 上传操作量 =====================
with tab_dict["📊 上传操作量"]:
    st.title("📊 操作量数据上传")
    st.markdown("""
    ---
    ### 📋 使用说明
    1. 点击下方 **"下载模板"** 按钮，下载 Excel 模板
    2. 按模板格式填写数据（**列名必须与模板完全一致**）
    3. 填写完成后，点击 **"选择文件"** 上传
    4. 系统将自动记录上传人和上传时间
    5. **同一站点+日期+班次的数据不可重复上传**
    ---
    """)
    st.subheader("📋 下载操作量模板")
    template_ops_df = pd.DataFrame({
        "biz_date": ["2026-06-01"],
        "station_code": ["CDC_SP"],
        "station_name": ["CDC SP"],
        "class_name": ["T1"],
        "is_conso": [0],
        "volume": [1500]
    })
    ops_output = BytesIO()
    with pd.ExcelWriter(ops_output, engine="openpyxl") as writer:
        template_ops_df.to_excel(writer, index=False, sheet_name="操作量数据")
    ops_template_bytes = ops_output.getvalue()
    col_ops_download, _ = st.columns([1, 3])
    with col_ops_download:
        st.download_button(
            label="📥 下载操作量模板 (Excel)",
            data=ops_template_bytes,
            file_name="操作量模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    st.caption("列名：biz_date、station_code、station_name、class_name、is_conso、volume（is_conso 为 0 或 1）")
    st.divider()
    st.subheader("📂 上传操作量文件")
    ops_uploaded_file = st.file_uploader("选择 Excel 或 CSV 文件", type=["xlsx", "xls", "csv"], key="ops_uploader")
    if ops_uploaded_file:
        try:
            df_ops = pd.read_excel(ops_uploaded_file) if not ops_uploaded_file.name.endswith(".csv") else pd.read_csv(ops_uploaded_file)
            if list(df_ops.columns) != OPS_COLS:
                st.error("❌ 列名与模板不一致！")
                st.write("模板列名：", OPS_COLS)
                st.write("您的列名：", list(df_ops.columns))
                st.stop()
            df_ops["biz_date"] = pd.to_datetime(df_ops["biz_date"]).dt.strftime("%Y-%m-%d")
            df_ops["volume"] = pd.to_numeric(df_ops["volume"])
            df_ops["is_conso"] = pd.to_numeric(df_ops["is_conso"])
            st.success(f"✅ 校验通过！共 {len(df_ops)} 行数据待上传")
            st.dataframe(df_ops.head(10), use_container_width=True)
            if st.button("✅ 确认上传操作量", use_container_width=True):
                with st.status("⏳ 正在上传操作量数据...", expanded=True) as status:
                    df_ops["上传人"] = user
                    df_ops["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    df_ops["版本号"] = datetime.now().strftime("%Y%m%d") + "V1"
                    success_count, fail_count = save_operations_to_db(df_ops)
                    if fail_count == 0:
                        status.update(label=f"✅ 上传完成！成功 {success_count} 条", state="complete")
                    else:
                        status.update(label=f"⚠️ 上传完成！成功 {success_count} 条，失败 {fail_count} 条", state="error")
                    st.write(f"👤 上传人：**{user}**")
                    st.write(f"📅 上传时间：**{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
                    st.write(f"📊 总行数：{len(df_ops)}")
                    if fail_count == 0:
                        st.success("🎉 所有操作量数据已成功上传！")
                        st.rerun()
                    else:
                        st.error(f"❌ 有 {fail_count} 行上传失败，请检查数据后重试")
        except Exception as e:
            st.error(f"❌ 读取文件失败：{e}")
    st.divider()
    st.subheader("📊 操作量数据总览")
    st.caption("展示已上传的操作量数据，可按年月和站点筛选")
    try:
        ops_df = get_operation_data()
        if len(ops_df) == 0:
            st.info("📭 暂无操作量数据，请先上传")
        else:
            ops_df["年月"] = pd.to_datetime(ops_df["日期"]).dt.strftime("%Y-%m")
            available_months_ops = sorted(ops_df["年月"].unique(), reverse=True)
            available_sites_ops = sorted(ops_df["仓库名称"].unique())
            col_f1_ops, col_f2_ops = st.columns(2)
            with col_f1_ops:
                selected_month_ops = st.selectbox("📅 选择年月", ["全部"] + available_months_ops, key="ops_month")
            with col_f2_ops:
                selected_site_ops = st.selectbox("🏢 选择站点", ["全部"] + available_sites_ops, key="ops_site")
            ops_filtered = ops_df.copy()
            if selected_month_ops != "全部":
                ops_filtered = ops_filtered[ops_filtered["年月"] == selected_month_ops]
            if selected_site_ops != "全部":
                ops_filtered = ops_filtered[ops_filtered["仓库名称"] == selected_site_ops]
            total_ops_records = len(ops_filtered)
            total_ops_volume = int(ops_filtered["操作量"].sum()) if total_ops_records > 0 else 0
            total_ops_sites = ops_filtered["仓库名称"].nunique()
            total_ops_days = ops_filtered["日期"].nunique()
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📋 总记录数", total_ops_records)
            col2.metric("📦 总操作量", f"{total_ops_volume:,}")
            col3.metric("🏢 站点数", total_ops_sites)
            col4.metric("📅 天数", total_ops_days)
            st.divider()
            st.subheader("🏢 各站点操作量汇总")
            station_summary = ops_filtered.groupby("仓库名称").agg({
                "操作量": "sum",
                "日期": "nunique"
            }).reset_index()
            station_summary.columns = ["站点名称", "总操作量", "天数"]
            station_summary["日均操作量"] = (station_summary["总操作量"] / station_summary["天数"]).round(0)
            st.dataframe(station_summary, use_container_width=True)
            st.subheader("📥 导出操作量数据")
            ops_csv = ops_filtered.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 导出操作量数据 (CSV)",
                data=ops_csv,
                file_name=f"操作量数据_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    except Exception as e:
        st.warning(f"⚠️ 读取操作量数据失败：{e}")

# ===================== Tab 价卡配置 =====================
with tab_dict["💰 价卡配置"]:
    st.title("💰 价卡配置")
    if not is_admin:
        st.warning("仅管理员（Ivy_Gao）可管理价卡配置")
        price_df = get_price_card_data()
        if len(price_df) > 0:
            st.subheader("📋 当前价卡列表")
            display_cols = [col for col in PRICE_CARD_COLS if col in price_df.columns]
            st.dataframe(price_df[display_cols], use_container_width=True)
        else:
            st.info("暂无价卡配置，请联系管理员上传")
        st.stop()
    st.success("管理员模式：可下载模板、上传价卡（版本控制，全量导入）")
    price_df = get_price_card_data()
    if len(price_df) > 0:
        latest_version = price_df["版本号"].max()
        st.info(f"📌 当前生效版本：**{latest_version}**")
    else:
        st.info("📌 暂无价卡配置，请上传")
    st.subheader("📋 下载价卡模板")
    price_template_df = pd.DataFrame({
        "区域": ["FM"],
        "仓库名称": ["TP IMN"],
        "供应商": ["Enfok"],
        "班次": ["T1"],
        "长期工_日结工": ["长期工"],
        "周日_非周日": ["周日"],
        "单价": [178],
        "生效时间": ["2026-04-01"],
        "失效时间": ["2099-12-31"]
    })
    price_output = BytesIO()
    with pd.ExcelWriter(price_output, engine="openpyxl") as writer:
        price_template_df.to_excel(writer, index=False, sheet_name="价卡配置")
    price_template_bytes = price_output.getvalue()
    col_t1, col_t2 = st.columns([1, 3])
    with col_t1:
        st.download_button(
            label="📥 下载价卡模板 (Excel)",
            data=price_template_bytes,
            file_name="价卡配置模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    st.caption("列名：区域、仓库名称、供应商、班次、长期工_日结工、周日_非周日、单价、生效时间、失效时间")
    st.divider()


    st.subheader("📤 上传价卡配置（自动生成版本）")
st.caption("每次上传将自动生成唯一版本号（时间戳），新版本将自动成为生效价卡。无需手动输入版本号。")
with st.form("upload_price_version_form"):
    # 移除了版本号输入框
    uploaded_price_file = st.file_uploader("选择 Excel 或 CSV", type=["xlsx", "xls", "csv"], key="price_uploader")
    submit_price = st.form_submit_button("确认上传")

if submit_price:
    if uploaded_price_file is None:
        st.error("❌ 请选择文件")
    else:
        try:
            df_price = pd.read_excel(uploaded_price_file) if not uploaded_price_file.name.endswith(".csv") else pd.read_csv(uploaded_price_file)
            if list(df_price.columns) != PRICE_CARD_COLS:
                st.error("❌ 列名与模板不一致！")
                st.write("模板列名：", PRICE_CARD_COLS)
                st.write("您的列名：", list(df_price.columns))
                st.stop()
            try:
                df_price["生效时间"] = pd.to_datetime(df_price["生效时间"]).dt.strftime("%Y-%m-%d")
                df_price["失效时间"] = pd.to_datetime(df_price["失效时间"]).dt.strftime("%Y-%m-%d")
            except Exception as e:
                st.error(f"❌ 日期格式有误：{e}")
                st.stop()
            try:
                df_price["单价"] = pd.to_numeric(df_price["单价"])
            except Exception as e:
                st.error(f"❌ 单价必须为数字：{e}")
                st.stop()

            # ===== 自动生成版本号（精确到秒，确保唯一且为最新） =====
            from datetime import datetime  # 脚本顶部已有，但为了明确可再写一次
            version_name = datetime.now().strftime("%Y%m%d%H%M%S")  # 例如 20260707153045

            # 不再检查是否存在，直接插入新版本（历史版本保留，但查询时取最大版本）
            df_price["上传人"] = user
            df_price["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df_price["版本号"] = version_name

            success_count, fail_count = save_price_card_to_db(df_price)
            if fail_count == 0:
                st.success(f"✅ 价卡配置上传成功！新版本号：{version_name}，共 {len(df_price)} 条")
                st.balloons()
                st.rerun()  # 刷新页面显示最新数据
            else:
                st.error(f"❌ 上传失败，请重试")
        except Exception as e:
            st.error(f"❌ 读取文件失败：{e}")
    st.divider()
    st.subheader("📋 当前价卡列表")
    price_df = get_price_card_data()
    if len(price_df) > 0:
        latest_version = price_df["版本号"].max()
        latest_df = price_df[price_df["版本号"] == latest_version]
        st.caption(f"✅ 当前版本：**{latest_version}** | 上传人：{latest_df['上传人'].iloc[0] if '上传人' in latest_df.columns else '-'}")
        display_cols = [col for col in PRICE_CARD_COLS if col in latest_df.columns]
        st.dataframe(latest_df[display_cols], use_container_width=True)
        st.subheader("📥 导出当前版本价卡")
        price_csv = latest_df[display_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"📥 导出价卡 ({latest_version})",
            data=price_csv,
            file_name=f"价卡配置_{latest_version}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        with st.expander("📜 查看所有历史版本"):
            version_summary = price_df.groupby("版本号").agg({
                "上传时间": "first",
                "区域": "count"
            }).reset_index()
            version_summary.columns = ["版本号", "上传时间", "记录数"]
            version_summary = version_summary.sort_values("上传时间", ascending=False)
            st.dataframe(version_summary, use_container_width=True)
            selected_version = st.selectbox(
                "选择版本查看详情",
                options=version_summary["版本号"].tolist()
            )
            if selected_version:
                version_detail = price_df[price_df["版本号"] == selected_version]
                detail_display = version_detail[display_cols]
                st.dataframe(detail_display, use_container_width=True)
                detail_csv = detail_display.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label=f"📥 导出 {selected_version}",
                    data=detail_csv,
                    file_name=f"价卡配置_{selected_version}.csv",
                    mime="text/csv"
                )
    else:
        st.info("暂无价卡配置，请上传")

# ========== 底部信息 ==========
st.caption(f"登录用户: {user} | 角色: {'管理员' if is_admin else '普通用户'} | 数据模式: 云端 TiDB")
