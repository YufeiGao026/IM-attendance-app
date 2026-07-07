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

# ========== 多语言支持 ==========

LANGUAGES = {
    "zh": "中文",
    "pt": "Português"
}

TRANSLATIONS = {
    # ---------- 通用 ----------
    "app_title": {"zh": "仓库出勤统计", "pt": "Estatística de Frequência do Armazém"},
    "login_title": {"zh": "🔐 登录", "pt": "🔐 Login"},
    "username": {"zh": "用户名", "pt": "Usuário"},
    "password": {"zh": "密码", "pt": "Senha"},
    "login_button": {"zh": "登录", "pt": "Entrar"},
    "login_error": {"zh": "❌ 用户名或密码错误", "pt": "❌ Usuário ou senha incorretos"},
    "logout": {"zh": "登出", "pt": "Sair"},
    "user_role_admin": {"zh": "管理员", "pt": "Administrador"},
    "user_role_user": {"zh": "普通用户", "pt": "Usuário comum"},
    "language_selector": {"zh": "🌐 语言 / Idioma", "pt": "🌐 Idioma / 语言"},
    "bottom_info": {"zh": "登录用户: {user} | 角色: {role} | 数据模式: 云端 TiDB", "pt": "Usuário: {user} | Função: {role} | Modo de dados: TiDB Cloud"},

    # ---------- 通用列名翻译 ----------
    "col_region": {"zh": "区域", "pt": "Região"},
    "col_warehouse": {"zh": "仓库", "pt": "Armazém"},
    "col_warehouse_name": {"zh": "仓库名称", "pt": "Nome do Armazém"},
    "col_date": {"zh": "日期", "pt": "Data"},
    "col_supplier": {"zh": "供应商", "pt": "Fornecedor"},
    "col_shift": {"zh": "班次", "pt": "Turno"},
    "col_worker_type": {"zh": "人员类型", "pt": "Tipo de Mão de Obra"},
    "col_people": {"zh": "人数", "pt": "Nº de Pessoas"},
    "col_volume": {"zh": "操作量", "pt": "Volume"},
    "col_unit_price": {"zh": "单价", "pt": "Preço Unitário"},
    "col_effective_date": {"zh": "生效时间", "pt": "Data de Vigência"},
    "col_expiry_date": {"zh": "失效时间", "pt": "Data de Expiração"},
    "col_sunday": {"zh": "周日_非周日", "pt": "Domingo/Não-Domingo"},
    "col_station": {"zh": "站点", "pt": "Estação"},
    "col_efficiency": {"zh": "人效", "pt": "Eficiência"},
    "col_daily_volume": {"zh": "日均操作量", "pt": "Volume Médio Diário"},
    "col_daily_headcount": {"zh": "日均出勤人数", "pt": "Frequência Média Diária"},
    "col_total_person_days": {"zh": "总出勤人天", "pt": "Total de Dias-pessoa"},
    "col_unit_cost": {"zh": "单人天成本", "pt": "Custo por Pessoa-dia"},

    # ---------- Tab 标题 ----------
    "tab_upload_attendance": {"zh": "📤 上传出勤数据", "pt": "📤 Carregar Frequência"},
    "tab_overview": {"zh": "📊 数据总览", "pt": "📊 Visão Geral"},
    "tab_efficiency": {"zh": "📈 外劳人效分析看板", "pt": "📈 Painel de Eficiência"},
    "tab_upload_ops": {"zh": "📊 上传操作量", "pt": "📊 Carregar Volume"},
    "tab_price_card": {"zh": "💰 价卡配置", "pt": "💰 Tabela de Preços"},

    # ---------- 上传出勤数据 ----------
    "attendance_title": {"zh": "📤 上传出勤数据", "pt": "📤 Carregar Frequência"},
    "attendance_instructions": {
        "zh": """
        ### 操作说明
        1. 选择 **日期范围** 和 **一个或多个仓库**。
        2. 点击 **"生成表格"**，系统会生成一个可编辑表格：
           - 前两列为 **仓库** 和 **日期**。
           - 其余列为 **供应商 → 班次 → 人员类型** 的三级表头。
        3. 在对应格子中填写出勤人数。
        4. 填写完毕后，点击 **"提交数据"**。
        """,
        "pt": """
        ### Instruções
        1. Selecione o **intervalo de datas** e **um ou mais armazéns**.
        2. Clique em **"Gerar Tabela"** para criar uma tabela editável:
           - As duas primeiras colunas são **Armazém** e **Data**.
           - As demais colunas têm cabeçalho de três níveis: **Fornecedor → Turno → Tipo de Mão de Obra**.
        3. Preencha o número de funcionários nas células correspondentes.
        4. Após preencher, clique em **"Enviar Dados"**.
        """
    },
    "attendance_start_date": {"zh": "📅 开始日期", "pt": "📅 Data Inicial"},
    "attendance_end_date": {"zh": "📅 结束日期", "pt": "📅 Data Final"},
    "attendance_select_warehouses": {"zh": "🏭 选择仓库（可多选）", "pt": "🏭 Selecionar Armazéns (múltiplos)"},
    "attendance_generate_btn": {"zh": "📋 生成表格", "pt": "📋 Gerar Tabela"},
    "attendance_no_warehouse_warning": {"zh": "⚠️ 请至少选择一个仓库", "pt": "⚠️ Selecione pelo menos um armazém"},
    "attendance_invalid_date_warning": {"zh": "⚠️ 日期范围无效", "pt": "⚠️ Intervalo de datas inválido"},
    "attendance_no_price_config": {"zh": "⚠️ 所选仓库在价卡表中无配置，请先上传价卡", "pt": "⚠️ Armazém selecionado não possui configuração na tabela de preços. Carregue a tabela primeiro."},
    "attendance_table_subheader": {"zh": "📋 出勤数据表格 ({rows} 行 × {cols} 列)", "pt": "📋 Tabela de Frequência ({rows} linhas × {cols} colunas)"},
    "attendance_submit_btn": {"zh": "📤 提交数据", "pt": "📤 Enviar Dados"},
    "attendance_clear_btn": {"zh": "🗑️ 清空表格", "pt": "🗑️ Limpar Tabela"},
    "attendance_no_data_warning": {"zh": "⚠️ 所有数值均为0，没有需要提交的数据", "pt": "⚠️ Todos os valores são 0, não há dados a enviar"},
    "attendance_no_records_warning": {"zh": "⚠️ 没有找到有效数据（大于0）", "pt": "⚠️ Nenhum dado válido encontrado (maior que 0)"},
    "attendance_success": {"zh": "✅ 全部 {count} 条数据上传成功！版本号：{version}", "pt": "✅ {count} registros enviados com sucesso! Versão: {version}"},
    "attendance_error": {"zh": "❌ 上传失败 {count} 条，请检查数据后重试", "pt": "❌ Falha ao enviar {count} registros. Verifique os dados e tente novamente."},
    "attendance_upload_error": {"zh": "❌ 上传出错：{error}", "pt": "❌ Erro ao enviar: {error}"},
    "attendance_download_template_caption": {"zh": "💡 下载 Excel 模板，表头为三层（供应商 → 班次 → 人员类型），无序号列，填写后复制粘贴到线上表格。", "pt": "💡 Baixe o modelo Excel com cabeçalho de três níveis (Fornecedor → Turno → Tipo). Preencha e copie para a tabela online."},
    "attendance_download_btn": {"zh": "📥 下载模板 (Excel)", "pt": "📥 Baixar Modelo (Excel)"},
    "attendance_info_generate": {"zh": "👆 请选择日期范围、仓库，并点击“生成表格”", "pt": "👆 Selecione o intervalo de datas e armazéns, e clique em “Gerar Tabela”"},

    # ---------- 数据总览 ----------
    "overview_title": {"zh": "📊 数据总览", "pt": "📊 Visão Geral dos Dados"},
    "overview_caption": {"zh": "仅展示每个仓库每月最新版本的数据，可通过筛选查看特定时间和站点", "pt": "Exibe apenas os dados da versão mais recente de cada armazém por mês. Filtre por período e estação."},
    "overview_month": {"zh": "📅 选择年月", "pt": "📅 Selecionar Mês/Ano"},
    "overview_site": {"zh": "🏢 选择站点", "pt": "🏢 Selecionar Estação"},
    "overview_warehouses": {"zh": "🏢 仓库数", "pt": "🏢 Armazéns"},
    "overview_total_people": {"zh": "👷 总外劳人数", "pt": "👷 Total de Funcionários"},
    "overview_total_records": {"zh": "📋 总记录数", "pt": "📋 Total de Registros"},
    "overview_uploaders": {"zh": "👤 上传人数", "pt": "👤 Uploaders"},
    "overview_warehouse_summary": {"zh": "🏢 各仓库汇总", "pt": "🏢 Resumo por Armazém"},
    "overview_export": {"zh": "📥 导出数据", "pt": "📥 Exportar Dados"},
    "overview_export_csv": {"zh": "📥 导出当前数据 (CSV)", "pt": "📥 Exportar dados atuais (CSV)"},
    "overview_no_data": {"zh": "📭 暂无数据，请先上传", "pt": "📭 Sem dados, faça o upload primeiro"},

    # ---------- 效率看板 ----------
    "efficiency_title": {"zh": "📈 外劳人效分析看板", "pt": "📈 Painel de Eficiência de Mão de Obra"},
    "efficiency_caption": {"zh": "核心指标：人效、日均操作量、日均出勤人数、总出勤人天、单人天成本", "pt": "Indicadores principais: Eficiência, Volume Médio Diário, Frequência Média Diária, Total de Dias-pessoa, Custo por Pessoa-dia"},
    "efficiency_filters": {"zh": "🔍 筛选条件", "pt": "🔍 Filtros"},
    "efficiency_month": {"zh": "年月", "pt": "Mês/Ano"},
    "efficiency_region": {"zh": "国家/区域", "pt": "País/Região"},
    "efficiency_site": {"zh": "站点", "pt": "Estação"},
    "efficiency_no_data": {"zh": "📭 当前无数据，请先上传出勤数据和操作量数据", "pt": "📭 Sem dados. Carregue os dados de frequência e volume primeiro."},
    "efficiency_read_error": {"zh": "❌ 读取数据失败：{error}", "pt": "❌ Falha ao ler dados: {error}"},
    "efficiency_filter_no_data": {"zh": "该筛选条件下无数据", "pt": "Nenhum dado para este filtro"},
    "efficiency_core_metrics": {"zh": "📊 核心指标", "pt": "📊 Indicadores Principais"},
    "efficiency_metric_efficiency": {"zh": "人效", "pt": "Eficiência"},
    "efficiency_metric_daily_volume": {"zh": "日均操作量", "pt": "Volume Médio Diário"},
    "efficiency_metric_daily_headcount": {"zh": "日均出勤人数", "pt": "Frequência Média Diária"},
    "efficiency_metric_total_person_days": {"zh": "总出勤人天", "pt": "Total de Dias-pessoa"},
    "efficiency_metric_unit_cost": {"zh": "单人天成本", "pt": "Custo por Pessoa-dia"},
    "efficiency_metric_unit": {"zh": "📌 人效单位：票/人/天 | 日均操作量单位：票 | 日均出勤人数单位：人 | 总出勤人天单位：人天 | 单人天成本单位：R$", "pt": "📌 Unidades: Eficiência: tickets/pessoa/dia | Volume médio: tickets | Frequência média: pessoas | Dias-pessoa: pessoa-dia | Custo: R$"},
    "efficiency_station_summary": {"zh": "📋 各站点汇总", "pt": "📋 Resumo por Estação"},
    "efficiency_export": {"zh": "📥 导出数据", "pt": "📥 Exportar Dados"},
    "efficiency_export_csv": {"zh": "📥 导出当前汇总 (CSV)", "pt": "📥 Exportar resumo atual (CSV)"},

    # ---------- 上传操作量 ----------
    "ops_title": {"zh": "📊 操作量数据上传", "pt": "📊 Carregar Volume de Operações"},
    "ops_instructions": {
        "zh": """
        ---
        ### 📋 使用说明
        1. 点击下方 **"下载模板"** 按钮，下载 Excel 模板
        2. 按模板格式填写数据（**列名必须与模板完全一致**）
        3. 填写完成后，点击 **"选择文件"** 上传
        4. 系统将自动记录上传人和上传时间
        5. **同一站点+日期+班次的数据不可重复上传**
        """,
        "pt": """
        ---
        ### 📋 Instruções
        1. Clique no botão **"Baixar Modelo"** abaixo para baixar o modelo Excel.
        2. Preencha os dados conforme o modelo (**os nomes das colunas devem corresponder exatamente**).
        3. Após preencher, clique em **"Selecionar arquivo"** para fazer o upload.
        4. O sistema registrará automaticamente o uploader e a data/hora.
        5. **Dados duplicados para o mesmo armazém+data+turno não são permitidos.**
        """
    },
    "ops_download_template_btn": {"zh": "📥 下载操作量模板 (Excel)", "pt": "📥 Baixar Modelo de Volume (Excel)"},
    "ops_upload_file": {"zh": "📂 上传操作量文件", "pt": "📂 Carregar arquivo de volume"},
    "ops_choose_file": {"zh": "选择 Excel 或 CSV 文件", "pt": "Selecione arquivo Excel ou CSV"},
    "ops_invalid_columns": {"zh": "❌ 列名与模板不一致！", "pt": "❌ Os nomes das colunas não correspondem ao modelo!"},
    "ops_validation_passed": {"zh": "✅ 校验通过！共 {count} 行数据待上传", "pt": "✅ Validação aprovada! {count} linhas prontas para upload"},
    "ops_submit_btn": {"zh": "✅ 确认上传操作量", "pt": "✅ Confirmar upload de volume"},
    "ops_uploading_status": {"zh": "⏳ 正在上传操作量数据...", "pt": "⏳ Enviando dados de volume..."},
    "ops_upload_success_status": {"zh": "✅ 上传完成！成功 {count} 条", "pt": "✅ Upload concluído! {count} registros"},
    "ops_upload_warning_status": {"zh": "⚠️ 上传完成！成功 {count} 条，失败 {fail} 条", "pt": "⚠️ Upload concluído! {count} sucessos, {fail} falhas"},
    "ops_upload_success": {"zh": "🎉 所有操作量数据已成功上传！", "pt": "🎉 Todos os dados de volume foram enviados com sucesso!"},
    "ops_upload_error": {"zh": "❌ 有 {count} 行上传失败，请检查数据后重试", "pt": "❌ {count} registros falharam. Verifique os dados e tente novamente."},
    "ops_read_error": {"zh": "❌ 读取文件失败：{error}", "pt": "❌ Falha ao ler o arquivo: {error}"},
    "ops_overview_title": {"zh": "📊 操作量数据总览", "pt": "📊 Visão Geral do Volume"},
    "ops_overview_caption": {"zh": "展示已上传的操作量数据，可按年月和站点筛选", "pt": "Exibe dados de volume já enviados. Filtre por mês/ano e estação."},
    "ops_no_data": {"zh": "📭 暂无操作量数据，请先上传", "pt": "📭 Sem dados de volume. Faça o upload primeiro."},
    "ops_month": {"zh": "📅 选择年月", "pt": "📅 Selecionar Mês/Ano"},
    "ops_site": {"zh": "🏢 选择站点", "pt": "🏢 Selecionar Estação"},
    "ops_total_records": {"zh": "📋 总记录数", "pt": "📋 Total de Registros"},
    "ops_total_volume": {"zh": "📦 总操作量", "pt": "📦 Volume Total"},
    "ops_warehouses": {"zh": "🏢 站点数", "pt": "🏢 Número de Estações"},
    "ops_days": {"zh": "📅 天数", "pt": "📅 Dias"},
    "ops_station_summary": {"zh": "🏢 各站点操作量汇总", "pt": "🏢 Resumo por Estação"},
    "ops_export": {"zh": "📥 导出操作量数据", "pt": "📥 Exportar dados de volume"},
    "ops_export_csv": {"zh": "📥 导出操作量数据 (CSV)", "pt": "📥 Exportar dados de volume (CSV)"},
    "ops_read_data_error": {"zh": "⚠️ 读取操作量数据失败：{error}", "pt": "⚠️ Falha ao ler dados de volume: {error}"},

    # ---------- 价卡配置 ----------
    "price_title": {"zh": "💰 价卡配置", "pt": "💰 Tabela de Preços"},
    "price_admin_only": {"zh": "仅管理员（Ivy_Gao）可管理价卡配置", "pt": "Apenas o administrador (Ivy_Gao) pode gerenciar a tabela de preços"},
    "price_current_list": {"zh": "📋 当前价卡列表", "pt": "📋 Lista de Preços Atual"},
    "price_no_config": {"zh": "暂无价卡配置，请联系管理员上传", "pt": "Nenhuma tabela de preços configurada. Entre em contato com o administrador."},
    "price_admin_mode": {"zh": "管理员模式：可下载模板、上传价卡（版本控制，全量导入）", "pt": "Modo administrador: Baixe o modelo, carregue a tabela de preços (controle de versão, importação completa)"},
    "price_current_version": {"zh": "📌 当前生效版本：**{version}**", "pt": "📌 Versão atual: **{version}**"},
    "price_no_version": {"zh": "📌 暂无价卡配置，请上传", "pt": "📌 Nenhuma tabela de preços. Faça o upload."},
    "price_download_template": {"zh": "📋 下载价卡模板", "pt": "📋 Baixar Modelo de Preços"},
    "price_download_btn": {"zh": "📥 下载价卡模板 (Excel)", "pt": "📥 Baixar Modelo (Excel)"},
    "price_template_cols": {"zh": "列名：区域、仓库名称、供应商、班次、长期工_日结工、周日_非周日、单价、生效时间、失效时间", "pt": "Colunas: Região, Armazém, Fornecedor, Turno, Mão de Obra, Domingo/Não-Domingo, Preço Unitário, Data de Vigência, Data de Expiração"},
    "price_upload_instruction": {"zh": "📤 上传价卡配置（自动生成版本）", "pt": "📤 Carregar Tabela de Preços (versão automática)"},
    "price_upload_caption": {"zh": "每次上传将自动生成唯一版本号（时间戳），新版本将自动成为生效价卡。无需手动输入版本号。", "pt": "Cada upload gera automaticamente um número de versão único (timestamp). A nova versão se tornará automaticamente a tabela de preços ativa."},
    "price_choose_file": {"zh": "选择 Excel 或 CSV", "pt": "Selecionar Excel ou CSV"},
    "price_submit_btn": {"zh": "确认上传", "pt": "Confirmar Upload"},
    "price_missing_file": {"zh": "❌ 请选择文件", "pt": "❌ Selecione um arquivo"},
    "price_invalid_columns": {"zh": "❌ 列名与模板不一致！", "pt": "❌ Os nomes das colunas não correspondem ao modelo!"},
    "price_date_error": {"zh": "❌ 日期格式有误：{error}", "pt": "❌ Formato de data inválido: {error}"},
    "price_price_error": {"zh": "❌ 单价必须为数字：{error}", "pt": "❌ O preço unitário deve ser um número: {error}"},
    "price_upload_success": {"zh": "✅ 价卡配置上传成功！新版本号：{version}，共 {count} 条", "pt": "✅ Tabela de preços enviada com sucesso! Nova versão: {version}, {count} registros"},
    "price_upload_error": {"zh": "❌ 上传失败，请重试", "pt": "❌ Falha no upload. Tente novamente."},
    "price_read_error": {"zh": "❌ 读取文件失败：{error}", "pt": "❌ Falha ao ler o arquivo: {error}"},
    "price_current_version_detail": {"zh": "✅ 当前版本：**{version}** | 上传人：{uploader}", "pt": "✅ Versão atual: **{version}** | Uploader: {uploader}"},
    "price_export_current": {"zh": "📥 导出当前版本价卡", "pt": "📥 Exportar tabela de preços atual"},
    "price_export_btn": {"zh": "📥 导出价卡 ({version})", "pt": "📥 Exportar Preços ({version})"},
    "price_history_expander": {"zh": "📜 查看所有历史版本", "pt": "📜 Ver todas as versões anteriores"},
    "price_history_version": {"zh": "版本号", "pt": "Versão"},
    "price_history_upload_time": {"zh": "上传时间", "pt": "Data/Hora do Upload"},
    "price_history_records": {"zh": "记录数", "pt": "Registros"},
    "price_select_version": {"zh": "选择版本查看详情", "pt": "Selecione a versão para ver detalhes"},
    "price_export_version_btn": {"zh": "📥 导出 {version}", "pt": "📥 Exportar {version}"},

    # ---------- 错误/状态 ----------
    "db_init_error": {"zh": "数据库引擎初始化失败: {error}", "pt": "Falha ao inicializar o motor do banco de dados: {error}"},
    "db_retry_warning": {"zh": "数据库连接超时，正在重试 ({attempt}/{max})...", "pt": "Tempo limite de conexão com o banco de dados. Tentando novamente ({attempt}/{max})..."},
    "db_retry_error": {"zh": "重试{max}次后仍失败: {error}", "pt": "Falha após {max} tentativas: {error}"}
}

def _t(key, **kwargs):
    lang = st.session_state.get("language", "zh")
    text = TRANSLATIONS.get(key, {}).get(lang, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text

if "language" not in st.session_state:
    st.session_state.language = "zh"

# ========== 页面配置 ==========
st.set_page_config(page_title=_t("app_title"), layout="wide")

# ========== 日志配置 ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== 硬编码配置 ==========
DB_HOST = "gateway01.us-east-1.prod.aws.tidbcloud.com"
DB_PORT = 4000
DB_USER = "3CPzLRo7kXD4JE5.root"
DB_PASSWORD = "jdJwdm2QejFDajX4"
DB_NAME = "attendance_db"

VALID_USERNAME = "Ivy_Gao"
VALID_PASSWORD = "IM_AttendanceData_2606"
ADMIN_USERS = ["Ivy_Gao"]
ALLOWED_USERS = ["Ivy_Gao", "Tiffany"]

STANDARD_COLS = ["区域", "仓库名称", "日期", "供应商", "班次", "长期工_日结工", "人数"]
PRICE_CARD_COLS = ["区域", "仓库名称", "供应商", "班次", "长期工_日结工", "周日_非周日", "单价", "生效时间", "失效时间"]
OPS_COLS = ["biz_date", "station_code", "station_name", "class_name", "is_conso", "volume"]

REGION_MAPPING = {
    "CDC SP": "东南区", "CDC RJ": "南区", "CDC MG": "北区",
    "TP BAR": "FM", "TP IMN": "FM", "TP IMG": "FM",
    "PA GUA": "东南区", "Drop BRA": "南区", "GLP Guarulhos": "东南区",
}

@st.cache_resource
def init_db_engine():
    try:
        url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=280, pool_size=5, max_overflow=10, connect_args={'connect_timeout': 30})
        return engine
    except Exception as e:
        st.error(_t("db_init_error", error=str(e)))
        raise

def get_db_connection():
    engine = init_db_engine()
    return engine.connect()

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
                            st.warning(_t("db_retry_warning", attempt=attempt+1, max=max_retries))
                            time.sleep(delay)
                            st.cache_resource.clear()
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

def get_latest_attendance(user=None):
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
    engine = init_db_engine()
    with engine.connect() as conn:
        if version:
            query = "SELECT * FROM price_card WHERE 版本号 = :version"
            df = pd.read_sql(text(query), conn, params={"version": version})
        else:
            query = """
                SELECT * FROM price_card 
                WHERE 上传时间 = (SELECT MAX(上传时间) FROM price_card)
            """
            df = pd.read_sql(text(query), conn)
        return df

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

def calculate_cost(price_df, date, warehouse, shift, worker_type, is_sunday_or_holiday, supplier):
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
        default = 180.0 if worker_type == "长期工" else 154.0
        return default

def get_work_days_for_month(ym_str):
    year, month = map(int, ym_str.split('-'))
    _, num_days = calendar.monthrange(year, month)
    sundays = sum(1 for day in range(1, num_days+1) if datetime(year, month, day).weekday() == 6)
    return num_days - sundays

def generate_efficiency_data(month=None, region=None, warehouse=None):
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

def generate_version(warehouse, work_date):
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
    dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(60)]
    warehouses = ["CDC SP", "CDC RJ", "CDC MG", "TP BAR", "TP IMN", "TP IMG", "PA GUA", "Drop BRA", "GLP Guarulhos"]
    data = []
    for wh in warehouses:
        for d in dates:
            volume = random.randint(500, 3500)
            data.append({"仓库名称": wh, "日期": d, "操作量": volume})
    return pd.DataFrame(data)

def validate_attendance_data(df):
    errors = []
    required = STANDARD_COLS
    if list(df.columns) != required:
        errors.append(f"列名不匹配，期望: {required}，实际: {list(df.columns)}")
        return errors
    try:
        pd.to_datetime(df["日期"])
    except:
        errors.append("日期列格式不正确，请使用 YYYY-MM-DD")
    if not df["人数"].apply(lambda x: isinstance(x, (int, float)) and x >= 0).all():
        errors.append("人数必须为非负整数（可以为0）")
    return errors

# ========== Session State ==========
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "db_connected" not in st.session_state:
    st.session_state.db_connected = False

# ========== 登录界面 ==========
if not st.session_state.logged_in:
    st.title(_t("login_title"))
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input(_t("username"))
        password = st.text_input(_t("password"), type="password")
        if st.button(_t("login_button"), use_container_width=True):
            if username == VALID_USERNAME and password == VALID_PASSWORD:
                st.session_state.logged_in = True
                st.session_state.user = username
                st.rerun()
            else:
                st.error(_t("login_error"))
    st.stop()

user = st.session_state.user
is_admin = user in ADMIN_USERS

# ========== 侧边栏 ==========
with st.sidebar:
    st.selectbox(
        _t("language_selector"),
        options=list(LANGUAGES.keys()),
        format_func=lambda x: LANGUAGES[x],
        key="language",
        on_change=lambda: st.rerun()
    )
    st.divider()
    role_text = _t("user_role_admin") if is_admin else _t("user_role_user")
    st.write(f"👤 {user} ({role_text})")
    if st.button(_t("logout") + " / Sair"):
        st.session_state.logged_in = False
        st.rerun()

# ========== 主界面 ==========
tab_names_fixed = ["📤 上传出勤数据", "📊 数据总览", "📈 外劳人效分析看板", "📊 上传操作量", "💰 价卡配置"]
tabs = st.tabs(tab_names_fixed)
tab_dict = {
    "📤 上传出勤数据": tabs[0],
    "📊 数据总览": tabs[1],
    "📈 外劳人效分析看板": tabs[2],
    "📊 上传操作量": tabs[3],
    "💰 价卡配置": tabs[4]
}

# ===================== Tab 上传出勤数据 =====================
with tab_dict["📤 上传出勤数据"]:
    st.title(_t("attendance_title"))
    st.markdown(_t("attendance_instructions"))

    # 区域和仓库清单（不变）
    REGION_WAREHOUSE_MAPPING = {
        "Middle West": ["DC-DF2", "DC-MT2", "RDC-GO2", "RDC-TO1"],
        "North": ["DC-PA4"],
        "North East": ["DC-BA3", "DC-PE2", "DC-PI2", "RDC-BA1"],
        "South East": ["RDC-MG1", "RDC-RJ1", "DC-ES2", "DS BHZI"],
        "SP": [
            "CDC-SP", "PA GUA", "RDC-SP1", "RDC-SP2", "RDC-SP4",
            "CDC-GU", "Drop BRA", "GLP Guarulhos", "PA MELI", "TP BAR",
            "PA SAT", "PA NVS", "TP IMN", "DS TAMI", "DS BUXI",
            "DS GRUI", "TP IMG"
        ],
        "South": ["RDC-RS2", "RDC-PR1", "DS JMSA", "RDC-SC1"],
    }
    ALL_WAREHOUSES = []
    for region, warehouses in REGION_WAREHOUSE_MAPPING.items():
        for wh in warehouses:
            ALL_WAREHOUSES.append(wh)
    REGION_MAPPING = {}
    for region, warehouses in REGION_WAREHOUSE_MAPPING.items():
        for wh in warehouses:
            REGION_MAPPING[wh] = region

    SUPPLIER_ORDER = ["D0", "Blitz", "Enfok", "Brevi", "Mission", "Polly", "GNX"]
    WORKER_ORDER = ["长期工", "日结工"]

    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        start_date = st.date_input(_t("attendance_start_date"), value=datetime.now().replace(day=1))
    with col2:
        end_date = st.date_input(_t("attendance_end_date"), value=datetime.now())
    with col3:
        selected_warehouses = st.multiselect(_t("attendance_select_warehouses"), ALL_WAREHOUSES, default=ALL_WAREHOUSES[:1] if ALL_WAREHOUSES else [])

    @st.cache_data(ttl=600)
    def get_column_combos(warehouses):
        price_df = get_price_card_data()
        if price_df.empty:
            return []
        filtered = price_df[price_df["仓库名称"].isin(warehouses)]
        if filtered.empty:
            return []
        combos = filtered[["供应商", "班次", "长期工_日结工"]].drop_duplicates().values.tolist()
        supplier_order_dict = {s: i for i, s in enumerate(SUPPLIER_ORDER)}
        worker_order_dict = {w: i for i, w in enumerate(WORKER_ORDER)}
        combos.sort(key=lambda x: (supplier_order_dict.get(x[0], 999), x[1], worker_order_dict.get(x[2], 999)))
        return combos

    if st.button(_t("attendance_generate_btn"), use_container_width=True):
        if not selected_warehouses:
            st.warning(_t("attendance_no_warehouse_warning"))
        else:
            dates = pd.date_range(start=start_date, end=end_date, freq='D').strftime("%Y-%m-%d").tolist()
            if not dates:
                st.warning(_t("attendance_invalid_date_warning"))
            else:
                combos = get_column_combos(selected_warehouses)
                if not combos:
                    st.warning(_t("attendance_no_price_config"))
                else:
                    # 使用翻译后的列名
                    wh_label = _t("col_warehouse")
                    date_label = _t("col_date")
                    supplier_label = _t("col_supplier")
                    shift_label = _t("col_shift")
                    worker_label = _t("col_worker_type")
                    col_tuples = [(wh_label, wh_label, wh_label), (date_label, date_label, date_label)] + [(supplier, shift, worker) for supplier, shift, worker in combos]
                    col_index = pd.MultiIndex.from_tuples(col_tuples, names=[supplier_label, shift_label, worker_label])
                    rows = []
                    for wh in selected_warehouses:
                        for d in dates:
                            row_data = [wh, d] + [0] * len(combos)
                            rows.append(row_data)
                    df_template = pd.DataFrame(rows, columns=col_index)
                    st.session_state["attendance_wide_df"] = df_template
                    st.session_state["attendance_wide_selected"] = {
                        "warehouses": selected_warehouses,
                        "dates": dates,
                        "combos": combos,
                    }
                    st.rerun()

    if "attendance_wide_df" in st.session_state:
        df_wide = st.session_state["attendance_wide_df"]
        st.subheader(_t("attendance_table_subheader", rows=len(df_wide), cols=len(df_wide.columns)))
        edited_df = st.data_editor(df_wide, use_container_width=True, key="attendance_wide_editor", num_rows="fixed")
        st.session_state["attendance_wide_df"] = edited_df

        col_submit, col_clear = st.columns([2, 1])
        with col_submit:
            if st.button(_t("attendance_submit_btn"), type="primary", use_container_width=True):
                original_warehouses = st.session_state["attendance_wide_selected"]["warehouses"]
                original_dates = st.session_state["attendance_wide_selected"]["dates"]
                combos = st.session_state["attendance_wide_selected"]["combos"]
                numeric_cols = edited_df.columns[2:]
                if edited_df[numeric_cols].eq(0).all().all():
                    st.warning(_t("attendance_no_data_warning"))
                else:
                    records = []
                    row_idx = 0
                    for wh in original_warehouses:
                        for d in original_dates:
                            row_data = edited_df.iloc[row_idx]
                            for col_tuple in numeric_cols:
                                if len(col_tuple) == 3:
                                    supplier, shift, worker = col_tuple
                                else:
                                    continue
                                val = row_data[col_tuple]
                                if val and val > 0:
                                    region = REGION_MAPPING.get(wh, "未知")
                                    records.append({
                                        "区域": region,
                                        "仓库名称": wh,
                                        "日期": d,
                                        "供应商": supplier,
                                        "班次": shift,
                                        "长期工_日结工": worker,
                                        "人数": int(val)
                                    })
                            row_idx += 1
                    if not records:
                        st.warning(_t("attendance_no_records_warning"))
                    else:
                        df_to_submit = pd.DataFrame(records)
                        first_warehouse = records[0]["仓库名称"]
                        today = datetime.now().strftime("%Y-%m-%d")
                        version = generate_version(first_warehouse, today)
                        df_to_submit["上传人"] = user
                        df_to_submit["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df_to_submit["版本号"] = version
                        try:
                            success_count, fail_count = save_attendance_to_db(df_to_submit)
                            if fail_count == 0:
                                st.success(_t("attendance_success", count=success_count, version=version))
                                st.balloons()
                                zero_rows = []
                                for wh in original_warehouses:
                                    for d in original_dates:
                                        zero_rows.append([wh, d] + [0] * len(combos))
                                st.session_state["attendance_wide_df"] = pd.DataFrame(zero_rows, columns=edited_df.columns)
                            else:
                                st.error(_t("attendance_error", count=fail_count))
                        except Exception as e:
                            st.error(_t("attendance_upload_error", error=str(e)))
        with col_clear:
            if st.button(_t("attendance_clear_btn"), use_container_width=True):
                if "attendance_wide_df" in st.session_state:
                    original_warehouses = st.session_state["attendance_wide_selected"]["warehouses"]
                    original_dates = st.session_state["attendance_wide_selected"]["dates"]
                    combos = st.session_state["attendance_wide_selected"]["combos"]
                    zero_rows = []
                    for wh in original_warehouses:
                        for d in original_dates:
                            zero_rows.append([wh, d] + [0] * len(combos))
                    st.session_state["attendance_wide_df"] = pd.DataFrame(zero_rows, columns=st.session_state["attendance_wide_df"].columns)
    else:
        st.info(_t("attendance_info_generate"))

    # 模板下载（使用翻译后的列名）
    st.divider()
    st.caption(_t("attendance_download_template_caption"))
    if selected_warehouses:
        combos_sample = get_column_combos(selected_warehouses)
        if combos_sample:
            sample_wh = selected_warehouses[0]
            sample_date = datetime.now().strftime("%Y-%m-%d")
            from collections import defaultdict
            supplier_groups = defaultdict(lambda: defaultdict(list))
            for s, sh, w in combos_sample:
                supplier_groups[s][sh].append(w)
            suppliers = list(supplier_groups.keys())
            total_data_cols = 0
            for s in suppliers:
                shifts = supplier_groups[s]
                total_data_cols += sum(len(shifts[sh]) for sh in list(shifts.keys()))
            total_cols = 2 + total_data_cols

            from openpyxl import Workbook
            from openpyxl.utils import get_column_letter
            from openpyxl.styles import Alignment, Font, Border, Side

            wb = Workbook()
            ws = wb.active
            ws.title = "出勤数据"
            for i in range(1, total_cols+1):
                if i <= 2:
                    ws.column_dimensions[get_column_letter(i)].width = 15
                else:
                    ws.column_dimensions[get_column_letter(i)].width = 12

            wh_label = _t("col_warehouse")
            date_label = _t("col_date")
            ws.merge_cells(start_row=1, start_column=1, end_row=3, end_column=1)
            ws.cell(row=1, column=1, value=wh_label)
            ws.merge_cells(start_row=1, start_column=2, end_row=3, end_column=2)
            ws.cell(row=1, column=2, value=date_label)

            col_idx = 3
            for supplier in suppliers:
                shifts = supplier_groups[supplier]
                shift_list = list(shifts.keys())
                supplier_col_count = sum(len(shifts[sh]) for sh in shift_list)
                if supplier_col_count > 1:
                    ws.merge_cells(start_row=1, start_column=col_idx, end_row=1, end_column=col_idx+supplier_col_count-1)
                ws.cell(row=1, column=col_idx, value=supplier)
                for shift in shift_list:
                    worker_list = shifts[shift]
                    shift_col_count = len(worker_list)
                    if shift_col_count > 1:
                        ws.merge_cells(start_row=2, start_column=col_idx, end_row=2, end_column=col_idx+shift_col_count-1)
                    ws.cell(row=2, column=col_idx, value=shift)
                    for worker in worker_list:
                        ws.cell(row=3, column=col_idx, value=worker)
                        col_idx += 1

            for row in range(1, 4):
                for col in range(1, total_cols+1):
                    cell = ws.cell(row=row, column=col)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    cell.font = Font(bold=True)

            data_row = 4
            ws.cell(row=data_row, column=1, value=sample_wh)
            ws.cell(row=data_row, column=2, value=sample_date)
            for col in range(3, total_cols+1):
                ws.cell(row=data_row, column=col, value=0)

            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                 top=Side(style='thin'), bottom=Side(style='thin'))
            for row in range(1, data_row+1):
                for col in range(1, total_cols+1):
                    ws.cell(row=row, column=col).border = thin_border

            output = BytesIO()
            wb.save(output)
            template_bytes = output.getvalue()
            st.download_button(
                label=_t("attendance_download_btn"),
                data=template_bytes,
                file_name="出勤模板.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# ===================== Tab 数据总览 =====================
with tab_dict["📊 数据总览"]:
    st.title(_t("overview_title"))
    st.caption(_t("overview_caption"))
    df_raw = get_latest_attendance(user if not is_admin else None)
    if len(df_raw) == 0:
        st.info(_t("overview_no_data"))
    else:
        df_raw["年月"] = pd.to_datetime(df_raw["日期"]).dt.strftime("%Y-%m")
        available_months = sorted(df_raw["年月"].unique(), reverse=True)
        available_sites = sorted(df_raw["仓库名称"].unique())
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            selected_month = st.selectbox(_t("overview_month"), ["全部"] + available_months)
        with col_f2:
            selected_site = st.selectbox(_t("overview_site"), ["全部"] + available_sites)
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
        col1.metric(_t("overview_warehouses"), total_warehouses)
        col2.metric(_t("overview_total_people"), total_people)
        col3.metric(_t("overview_total_records"), total_records)
        col4.metric(_t("overview_uploaders"), total_uploaders)
        st.divider()
        # 重命名列名为翻译
        rename_map = {
            "区域": _t("col_region"),
            "仓库名称": _t("col_warehouse_name"),
            "日期": _t("col_date"),
            "供应商": _t("col_supplier"),
            "班次": _t("col_shift"),
            "长期工_日结工": _t("col_worker_type"),
            "人数": _t("col_people")
        }
        df_display = df_filtered.rename(columns=rename_map)
        st.dataframe(df_display, use_container_width=True)
        st.subheader(_t("overview_warehouse_summary"))
        warehouse_summary = df_filtered.groupby("仓库名称").agg({
            "人数": "sum",
            "区域": "first"
        }).reset_index()
        warehouse_summary.columns = ["仓库名称", "总人数", "区域"]
        warehouse_summary = warehouse_summary.rename(columns={
            "仓库名称": _t("col_warehouse_name"),
            "总人数": _t("col_people"),
            "区域": _t("col_region")
        })
        st.dataframe(warehouse_summary, use_container_width=True)
        st.subheader(_t("overview_export"))
        csv = df_filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=_t("overview_export_csv"),
            data=csv,
            file_name=f"仓库出勤汇总_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ===================== Tab 外劳人效分析看板 =====================
with tab_dict["📈 外劳人效分析看板"]:
    st.title(_t("efficiency_title"))
    st.caption(_t("efficiency_caption"))
    st.markdown("""
    <style>
    div[data-testid="metric-container"] .stMetricValue { font-size: 28px !important; }
    div[data-testid="metric-container"] .stMetricLabel { font-size: 14px !important; }
    div[data-testid="metric-container"] .stMetricDelta { font-size: 12px !important; }
    </style>
    """, unsafe_allow_html=True)
    try:
        merged = generate_efficiency_data()
        if len(merged) == 0:
            st.info(_t("efficiency_no_data"))
            st.stop()
    except Exception as e:
        st.error(_t("efficiency_read_error", error=str(e)))
        st.stop()
    available_months = sorted(merged["年月"].unique(), reverse=True)
    month_options = ["全部"] + available_months
    st.subheader(_t("efficiency_filters"))
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        selected_month = st.selectbox(_t("efficiency_month"), month_options, key="eff_month")
    with col_f2:
        regions = sorted(merged["区域"].unique())
        selected_region = st.selectbox(_t("efficiency_region"), ["全部"] + list(regions), key="eff_region")
    with col_f3:
        if selected_region == "全部":
            filtered_warehouses = sorted(merged["仓库名称"].unique())
        else:
            filtered_warehouses = sorted(merged[merged["区域"] == selected_region]["仓库名称"].unique())
        selected_warehouse = st.selectbox(_t("efficiency_site"), ["全部"] + list(filtered_warehouses), key="eff_site")
    filtered_df = merged.copy()
    if selected_month != "全部":
        filtered_df = filtered_df[filtered_df["年月"] == selected_month]
    if selected_region != "全部":
        filtered_df = filtered_df[filtered_df["区域"] == selected_region]
    if selected_warehouse != "全部":
        filtered_df = filtered_df[filtered_df["仓库名称"] == selected_warehouse]
    if len(filtered_df) == 0:
        st.warning(_t("efficiency_filter_no_data"))
        st.stop()
    price_df = get_price_card_data()
    actual_days = filtered_df["日期"].nunique()
    total_volume = int(filtered_df["操作量"].sum())
    total_person_days = filtered_df.groupby("日期")["人数"].sum().sum()
    avg_efficiency = filtered_df["人效"].mean() if len(filtered_df) > 0 else 0
    daily_volume = total_volume / actual_days if actual_days > 0 else 0
    daily_headcount = total_person_days / actual_days if actual_days > 0 else 0
    total_cost = 0.0
    for _, row in filtered_df.iterrows():
        date_obj = pd.to_datetime(row["日期"])
        is_sunday_or_holiday = (date_obj.weekday() == 6) or (date_obj.month == 5 and date_obj.day == 1)
        unit_price = calculate_cost(price_df, row["日期"], row["仓库名称"], row["班次"], row["长期工_日结工"], is_sunday_or_holiday, row["供应商"])
        total_cost += unit_price * row["人数"]
    unit_cost = total_cost / total_person_days if total_person_days > 0 else 0
    st.subheader(_t("efficiency_core_metrics"))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(_t("efficiency_metric_efficiency"), f"{avg_efficiency:.0f}")
    c2.metric(_t("efficiency_metric_daily_volume"), f"{daily_volume:,.0f}")
    c3.metric(_t("efficiency_metric_daily_headcount"), f"{daily_headcount:.0f}")
    c4.metric(_t("efficiency_metric_total_person_days"), f"{total_person_days:,.0f}")
    c5.metric(_t("efficiency_metric_unit_cost"), f"R${unit_cost:.2f}")
    st.caption(_t("efficiency_metric_unit"))
    st.subheader(_t("efficiency_station_summary"))
    stations = filtered_df["仓库名称"].unique()
    summary_rows = []
    for station in stations:
        station_df = filtered_df[filtered_df["仓库名称"] == station]
        region = station_df["区域"].iloc[0]
        station_days = station_df["日期"].nunique()
        vol = station_df["操作量"].sum()
        eff = station_df["人效"].mean()
        person_days = station_df.groupby("日期")["人数"].sum().sum()
        daily_vol_station = vol / station_days if station_days > 0 else 0
        daily_headcount_station = person_days / station_days if station_days > 0 else 0
        cost_station = 0.0
        for _, row in station_df.iterrows():
            date_obj = pd.to_datetime(row["日期"])
            is_sunday_or_holiday = (date_obj.weekday() == 6) or (date_obj.month == 5 and date_obj.day == 1)
            unit_price = calculate_cost(price_df, row["日期"], row["仓库名称"], row["班次"], row["长期工_日结工"], is_sunday_or_holiday, row["供应商"])
            cost_station += unit_price * row["人数"]
        unit_cost_station = cost_station / person_days if person_days > 0 else 0
        summary_rows.append({
            _t("col_region"): region,
            _t("col_station"): station,
            _t("col_efficiency"): f"{eff:.0f}",
            _t("col_daily_volume"): f"{daily_vol_station:.0f}",
            _t("col_daily_headcount"): f"{daily_headcount_station:.0f}",
            _t("col_total_person_days"): f"{person_days:,.0f}",
            _t("col_unit_cost"): f"R${unit_cost_station:.2f}"
        })
    result_df = pd.DataFrame(summary_rows)
    st.dataframe(result_df, use_container_width=True)
    st.subheader(_t("efficiency_export"))
    csv = result_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=_t("efficiency_export_csv"),
        data=csv,
        file_name=f"外劳人效分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

# ===================== Tab 上传操作量 =====================
with tab_dict["📊 上传操作量"]:
    st.title(_t("ops_title"))
    st.markdown(_t("ops_instructions"))
    st.subheader("📋 " + _t("ops_download_template_btn").replace("📥 ", ""))
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
            label=_t("ops_download_template_btn"),
            data=ops_template_bytes,
            file_name="操作量模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    st.caption("列名：biz_date、station_code、station_name、class_name、is_conso、volume（is_conso 为 0 或 1）")
    st.divider()
    st.subheader(_t("ops_upload_file"))
    ops_uploaded_file = st.file_uploader(_t("ops_choose_file"), type=["xlsx", "xls", "csv"], key="ops_uploader")
    if ops_uploaded_file:
        try:
            df_ops = pd.read_excel(ops_uploaded_file) if not ops_uploaded_file.name.endswith(".csv") else pd.read_csv(ops_uploaded_file)
            if list(df_ops.columns) != OPS_COLS:
                st.error(_t("ops_invalid_columns"))
                st.write("模板列名：", OPS_COLS)
                st.write("您的列名：", list(df_ops.columns))
                st.stop()
            df_ops["biz_date"] = pd.to_datetime(df_ops["biz_date"]).dt.strftime("%Y-%m-%d")
            df_ops["volume"] = pd.to_numeric(df_ops["volume"])
            df_ops["is_conso"] = pd.to_numeric(df_ops["is_conso"])
            st.success(_t("ops_validation_passed", count=len(df_ops)))
            st.dataframe(df_ops.head(10), use_container_width=True)
            if st.button(_t("ops_submit_btn"), use_container_width=True):
                with st.status(_t("ops_uploading_status"), expanded=True) as status:
                    df_ops["上传人"] = user
                    df_ops["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    df_ops["版本号"] = datetime.now().strftime("%Y%m%d") + "V1"
                    success_count, fail_count = save_operations_to_db(df_ops)
                    if fail_count == 0:
                        status.update(label=_t("ops_upload_success_status", count=success_count), state="complete")
                    else:
                        status.update(label=_t("ops_upload_warning_status", count=success_count, fail=fail_count), state="error")
                    st.write(f"👤 上传人：**{user}**")
                    st.write(f"📅 上传时间：**{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
                    st.write(f"📊 总行数：{len(df_ops)}")
                    if fail_count == 0:
                        st.success(_t("ops_upload_success"))
                        st.rerun()
                    else:
                        st.error(_t("ops_upload_error", count=fail_count))
        except Exception as e:
            st.error(_t("ops_read_error", error=str(e)))
    st.divider()
    st.subheader(_t("ops_overview_title"))
    st.caption(_t("ops_overview_caption"))
    try:
        ops_df = get_operation_data()
        if len(ops_df) == 0:
            st.info(_t("ops_no_data"))
        else:
            ops_df["年月"] = pd.to_datetime(ops_df["日期"]).dt.strftime("%Y-%m")
            available_months_ops = sorted(ops_df["年月"].unique(), reverse=True)
            available_sites_ops = sorted(ops_df["仓库名称"].unique())
            col_f1_ops, col_f2_ops = st.columns(2)
            with col_f1_ops:
                selected_month_ops = st.selectbox(_t("ops_month"), ["全部"] + available_months_ops, key="ops_month")
            with col_f2_ops:
                selected_site_ops = st.selectbox(_t("ops_site"), ["全部"] + available_sites_ops, key="ops_site")
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
            col1.metric(_t("ops_total_records"), total_ops_records)
            col2.metric(_t("ops_total_volume"), f"{total_ops_volume:,}")
            col3.metric(_t("ops_warehouses"), total_ops_sites)
            col4.metric(_t("ops_days"), total_ops_days)
            st.divider()
            st.subheader(_t("ops_station_summary"))
            station_summary = ops_filtered.groupby("仓库名称").agg({
                "操作量": "sum",
                "日期": "nunique"
            }).reset_index()
            station_summary.columns = ["站点名称", "总操作量", "天数"]
            station_summary["日均操作量"] = (station_summary["总操作量"] / station_summary["天数"]).round(0)
            station_summary = station_summary.rename(columns={
                "站点名称": _t("col_station"),
                "总操作量": _t("col_volume"),
                "天数": _t("col_days") if "col_days" in TRANSLATIONS else "Dias"
            })
            st.dataframe(station_summary, use_container_width=True)
            st.subheader(_t("ops_export"))
            ops_csv = ops_filtered.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label=_t("ops_export_csv"),
                data=ops_csv,
                file_name=f"操作量数据_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    except Exception as e:
        st.warning(_t("ops_read_data_error", error=str(e)))

# ===================== Tab 价卡配置 =====================
with tab_dict["💰 价卡配置"]:
    st.title(_t("price_title"))
    if not is_admin:
        st.warning(_t("price_admin_only"))
        price_df = get_price_card_data()
        if len(price_df) > 0:
            st.subheader(_t("price_current_list"))
            display_cols = [col for col in PRICE_CARD_COLS if col in price_df.columns]
            rename_map = {
                "区域": _t("col_region"),
                "仓库名称": _t("col_warehouse_name"),
                "供应商": _t("col_supplier"),
                "班次": _t("col_shift"),
                "长期工_日结工": _t("col_worker_type"),
                "周日_非周日": _t("col_sunday"),
                "单价": _t("col_unit_price"),
                "生效时间": _t("col_effective_date"),
                "失效时间": _t("col_expiry_date")
            }
            df_display = price_df[display_cols].rename(columns=rename_map)
            st.dataframe(df_display, use_container_width=True)
        else:
            st.info(_t("price_no_config"))
        st.stop()
    st.success(_t("price_admin_mode"))
    price_df = get_price_card_data()
    if len(price_df) > 0:
        latest_version = price_df["版本号"].max()
        st.info(_t("price_current_version", version=latest_version))
    else:
        st.info(_t("price_no_version"))
    st.subheader(_t("price_download_template"))
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
            label=_t("price_download_btn"),
            data=price_template_bytes,
            file_name="价卡配置模板.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    st.caption(_t("price_template_cols"))
    st.divider()

    st.subheader(_t("price_upload_instruction"))
    st.caption(_t("price_upload_caption"))
    with st.form("upload_price_version_form"):
        uploaded_price_file = st.file_uploader(_t("price_choose_file"), type=["xlsx", "xls", "csv"], key="price_uploader")
        submit_price = st.form_submit_button(_t("price_submit_btn"))
    if submit_price:
        if uploaded_price_file is None:
            st.error(_t("price_missing_file"))
        else:
            try:
                df_price = pd.read_excel(uploaded_price_file) if not uploaded_price_file.name.endswith(".csv") else pd.read_csv(uploaded_price_file)
                if list(df_price.columns) != PRICE_CARD_COLS:
                    st.error(_t("price_invalid_columns"))
                    st.write("模板列名：", PRICE_CARD_COLS)
                    st.write("您的列名：", list(df_price.columns))
                    st.stop()
                try:
                    df_price["生效时间"] = pd.to_datetime(df_price["生效时间"]).dt.strftime("%Y-%m-%d")
                    df_price["失效时间"] = pd.to_datetime(df_price["失效时间"]).dt.strftime("%Y-%m-%d")
                except Exception as e:
                    st.error(_t("price_date_error", error=str(e)))
                    st.stop()
                try:
                    df_price["单价"] = pd.to_numeric(df_price["单价"])
                except Exception as e:
                    st.error(_t("price_price_error", error=str(e)))
                    st.stop()
                version_name = datetime.now().strftime("%Y%m%d%H%M%S")
                df_price["上传人"] = user
                df_price["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                df_price["版本号"] = version_name
                success_count, fail_count = save_price_card_to_db(df_price)
                if fail_count == 0:
                    st.success(_t("price_upload_success", version=version_name, count=len(df_price)))
                    st.balloons()
                    st.rerun()
                else:
                    st.error(_t("price_upload_error"))
            except Exception as e:
                st.error(_t("price_read_error", error=str(e)))
    st.divider()
    st.subheader(_t("price_current_list"))
    price_df = get_price_card_data()
    if len(price_df) > 0:
        latest_version = price_df["版本号"].max()
        latest_df = price_df[price_df["版本号"] == latest_version]
        uploader_name = latest_df['上传人'].iloc[0] if '上传人' in latest_df.columns else '-'
        st.caption(_t("price_current_version_detail", version=latest_version, uploader=uploader_name))
        display_cols = [col for col in PRICE_CARD_COLS if col in latest_df.columns]
        rename_map = {
            "区域": _t("col_region"),
            "仓库名称": _t("col_warehouse_name"),
            "供应商": _t("col_supplier"),
            "班次": _t("col_shift"),
            "长期工_日结工": _t("col_worker_type"),
            "周日_非周日": _t("col_sunday"),
            "单价": _t("col_unit_price"),
            "生效时间": _t("col_effective_date"),
            "失效时间": _t("col_expiry_date")
        }
        df_display = latest_df[display_cols].rename(columns=rename_map)
        st.dataframe(df_display, use_container_width=True)
        st.subheader(_t("price_export_current"))
        price_csv = latest_df[display_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=_t("price_export_btn", version=latest_version),
            data=price_csv,
            file_name=f"价卡配置_{latest_version}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        with st.expander(_t("price_history_expander")):
            version_summary = price_df.groupby("版本号").agg({
                "上传时间": "first",
                "区域": "count"
            }).reset_index()
            version_summary.columns = [_t("price_history_version"), _t("price_history_upload_time"), _t("price_history_records")]
            version_summary = version_summary.sort_values(_t("price_history_upload_time"), ascending=False)
            st.dataframe(version_summary, use_container_width=True)
            selected_version = st.selectbox(
                _t("price_select_version"),
                options=version_summary[_t("price_history_version")].tolist()
            )
            if selected_version:
                version_detail = price_df[price_df["版本号"] == selected_version]
                detail_display = version_detail[display_cols].rename(columns=rename_map)
                st.dataframe(detail_display, use_container_width=True)
                detail_csv = version_detail[display_cols].to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label=_t("price_export_version_btn", version=selected_version),
                    data=detail_csv,
                    file_name=f"价卡配置_{selected_version}.csv",
                    mime="text/csv"
                )
    else:
        st.info(_t("price_no_config"))

# ========== 底部信息 ==========
role_text = _t("user_role_admin") if is_admin else _t("user_role_user")
st.caption(_t("bottom_info", user=user, role=role_text))
