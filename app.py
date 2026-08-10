# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
# 只有这些内容会触发 21 天复习提醒
WORD_ONLY_CONTENTS = ["单词", "大学单词", "雅思单词", "旧数据补录", "导入"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] # 0.5 到 10.0 小时
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# 初始化状态
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
if 'undo_cache' not in st.session_state:
    st.session_state['undo_cache'] = None

# -------------------------- 2. 核心工具函数 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        return r.json().get("tenant_access_token")
    except: return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        if not items: return pd.DataFrame()
        data = []
        for item in items:
            f = item["fields"]
            f["record_id"] = item["record_id"]
            data.append(f)
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 过滤掉本地临时计算字段
    forbidden = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt", "dt_obj", "统计课型", "序号", "总课时(h)", "上课日期", "日期文字"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden}
    try:
        r = requests.post(url, headers=headers, json={"fields": clean_f})
        return r.json()
    except: return {"code": -1}

def update_feishu_record(table_id, record_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.put(url, headers=headers, json={"fields": fields})
        return r.json()
    except: return {"code": -1}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers)
        return r.json()
    except: return {"code": -1}

def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]: return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]: return 50
    return 40 

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦"

# -------------------------- 3. 响应式黄金比例样式 (PC两列, 手机一列) --------------------------
st.set_page_config(page_title="FishTeacher", layout="centered", page_icon="🐟")
st.markdown("""
<style> /* 1. 限制电脑端最大宽度 */ .block-container { max-width: 850px !important; padding-top: 1rem !important; }
/* 2. 响应式列宽：手机端自动变一列并撑满 */
@media (max-width: 600px) {
[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
}
 /* 主功能按钮：横向拉长+居中，不再贴左侧 */
    div.stButton > button {
        width: 330px !important; /* 控制长方形横向长度，调大更宽 */
        height: 100px !important;
        margin: 0 auto 15px auto !important; /* 水平居中 */
        font-size: 22px !important;
        font-weight: bold !important;
        color: #FFFFFF !important;
        background-color: #21242c !important;
        border: 2px solid #5289f7 !important;
        border-radius: 20px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        padding-left: 25px !important;
        box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.3) !important;
    }
    div.stButton > button:active { background-color: #5289f7 !important; }
/* 1 级：主大标题 /
.brand-title {font-size: 32px;font-weight: bold;text-align: center;margin-bottom: 10px; }
/ 2 级：小标题 /
.brand-subtitle { font-size: 30px; color:#444444;text-align: center;margin-bottom: 10px; text-align: center;}
/ 3 级：更小的说明文本（新增） */
.brand-desc {font-size: 10px;color:#666666;text-align: center;margin-bottom: 15px;}
/* 5. 返回按钮样式 */
.back-btn-box div.stButton > button {
height: 55px !important; font-size: 16px !important; width: 300px !important;
background-color: transparent !important; border: 1px solid #555 !important;
justify-content: center !important; padding-left: 0 !important;
}
 /* 下拉弹窗每一条选项 */
    div[data-baseweb="popover"] ul li {
        min-height: 100px !important;
        font-size: 22px !important;
        padding: 12px 20px !important;
    }
    div[data-baseweb="popover"] ul {
        background-color: #1c1e24 !important;
        border-radius: 16px !important;
    }
    div[data-baseweb="popover"] ul li:hover {
        background-color: #333640 !important;
    }
    div[data-baseweb="popover"] ul li[aria-selected="true"] {
        background-color: #2a3142 !important;
    }
/* 隐藏页脚 */
footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)
# --- 全页面统一标题---
st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-subtitle"><strong>🐟 FishTeacher</strong></p>', unsafe_allow_html=True)
st.markdown('<p class="brand-desc">掌上拇指便捷管理</p>', unsafe_allow_html=True) 

# -------------------------- 4. 逻辑分发 --------------------------

if st.session_state['undo_cache']:
    if st.sidebar.button("🔙 撤销上次删除", type="primary"):
        add_feishu_record(st.session_state['undo_cache']['table'], st.session_state['undo_cache']['data'])
        st.session_state['undo_cache'] = None
        st.sidebar.success("已恢复！"); time.sleep(1); st.rerun()

def back_home():
    st.session_state['menu_choice'] = "首页"
    st.rerun()

# --- 首页菜单 ---
if st.session_state['menu_choice'] == "首页":
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 复习提醒"): st.session_state['menu_choice'] = "提醒"; st.rerun()
        if st.button("💰 财务核算"): st.session_state['menu_choice'] = "财务"; st.rerun()
        if st.button("👥 学生档案"): st.session_state['menu_choice'] = "名册"; st.rerun()
    with col2:
        if st.button("📝 快速录课"): st.session_state['menu_choice'] = "录入"; st.rerun()
        if st.button("📜 流水明细"): st.session_state['menu_choice'] = "明细"; st.rerun()
        if st.button("📄 导出21天"): st.session_state['menu_choice'] = "导出"; st.rerun()
    st.write("---")
    if st.button("📥 批量数据导入"): st.session_state['menu_choice'] = "导入"; st.rerun()

# --- 模块：提醒 ---
elif st.session_state['menu_choice'] == "提醒":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("选择提醒日期", datetime.date.today())
        target_s = st.selectbox("指定学员", ["全部学生"] + sorted(r_df['姓名'].unique().tolist()))
        reminders = {}
        for _, row in r_df.iterrows():
            if row['学习内容'] in WORD_ONLY_CONTENTS:
                diff = (q_date - row['dt']).days + 1
                if diff in REVIEW_DAYS:
                    n = row['姓名']
                    if target_s != "全部学生" and n != target_s: continue
                    if n not in reminders: reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**"); st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("今日该学生无复习任务")

# --- 模块：财务 ---
elif st.session_state['menu_choice'] == "财务":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        r_df['日期文字'] = r_df['dt_obj'].dt.strftime('%Y-%m-%d')
        target_m = st.selectbox("📅 选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        
        ca, cb = st.columns(2)
        ca.metric("总薪资", f"¥{m_df['小计'].sum():,.0f}")
        cb.metric("总时长", f"{m_df['课时'].sum():.1f}h")
        
        # 精准汇总 (合并单词和旧数据)
        def merge_c(c):
            if c in ["单词", "旧数据补录", "导入", "大学单词", "雅思单词"]: return "单词课(合并)"
            return c
        m_df['统计课型'] = m_df['学习内容'].apply(merge_c)
        s_sum = m_df.groupby(['姓名', '统计课型']).agg({'课时': 'sum', '小计': 'sum'}).reset_index()
        s_order = s_sum.groupby('姓名')['课时'].sum().reset_index().sort_values('课时', ascending=False)
        final = pd.merge(s_order[['姓名']], s_sum, on='姓名', how='left')
        final.insert(0, '序号', final['姓名'].map({n: i+1 for i, n in enumerate(s_order['姓名'].unique())}))
        st.dataframe(final, use_container_width=True, hide_index=True)
        
        st.write("---")
        search_n = st.selectbox("🔍 选择学生看上课明细记录", ["请选择"] + final['姓名'].unique().tolist())
        if search_n != "请选择":
            detail = m_df[m_df['姓名'] == search_n].sort_values(by='日期文字', ascending=False)
            st.dataframe(detail[['日期文字', '学习内容', '课时', '小计']], use_container_width=True, hide_index=True)

# --- 模块：录入 ---
elif st.session_state['menu_choice'] == "录入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("in"):
            name = st.selectbox("学生姓名", active_s); date = st.date_input("上课日期"); content = st.selectbox("内容", LEARN_CONTENTS); hour = st.selectbox("课时", HOURS_OPTIONS, index=1)
            if st.form_submit_button("确认录入"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success("同步成功")

# --- 模块：档案 ---
elif st.session_state['menu_choice'] == "名册":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    with st.expander("➕ 添加新学员"):
        with st.form("add"):
            n = st.text_input("姓名"); s = st.selectbox("状态", STATUS_OPTIONS); info = st.text_area("基础档案信息"); 
            if st.form_submit_button("确认入库"):
                if n: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s, "基础信息": info}); st.rerun()
    if not s_df.empty:
        ts = st.selectbox("📂 编辑/查看学生档案", ["未选择"] + sorted(s_df['姓名'].tolist()))
        if ts != "未选择":
            data = s_df[s_df['姓名'] == ts].iloc[0]
            with st.container(border=True):
                ns = st.selectbox("状态", STATUS_OPTIONS, index=STATUS_OPTIONS.index(data['状态']) if data['状态'] in STATUS_OPTIONS else 0)
                ni = st.text_area("信息文本框", value=data.get('基础信息', ""), height=200)
                c1, c2 = st.columns(2)
                if c1.button("💾 保存档案内容"):
                    update_feishu_record(TABLE_ID_STUDENTS, data['record_id'], {"状态": ns, "基础信息": ni}); st.success("已更新"); st.rerun()
                if c2.button("🗑️ 彻底删除学生"):
                    if st.checkbox("确认删除"): delete_feishu_record(TABLE_ID_STUDENTS, data['record_id']); st.rerun()

# --- 模块：明细、导出、导入 ---
elif st.session_state['menu_choice'] == "明细":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","日期","学习内容","课时"]], use_container_width=True, hide_index=True)
        t = st.selectbox("🗑️ 删除记录", ["请选择"] + (all_r['姓名']+" | "+all_r['日期']).tolist())
        if t != "请选择" and st.checkbox("确认"):
            if st.button("执行删除"):
                idx = (all_r['姓名']+" | "+all_r['日期']).tolist().index(t)
                st.session_state['undo_cache'] = {"table": TABLE_ID_RECORDS, "data": all_r.iloc[idx].to_dict()}
                delete_feishu_record(TABLE_ID_RECORDS, all_r.iloc[idx]['record_id']); st.rerun()

elif st.session_state['menu_choice'] == "导出":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("学员", sorted(r_all['姓名'].unique().tolist()))
        if st.button("生成"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']; rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO(); pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

elif st.session_state['menu_choice'] == "导入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f); bar = st.progress(0)
        if st.button("启动同步"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS); names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                if name not in names_in: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"}); names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date(); ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            st.success("完成")
