# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random
from collections import defaultdict

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_ONLY_CONTENTS = ["单词", "旧数据补录", "导入"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业", "更换教练"]
GRADE_OPTIONS = ["未填写", "小学", "初一", "初二", "初三", "高一", "高二", "高三", "大学", "成人"]
ANIMAL_EMOJIS = ["🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🐰", "🦆", "🐸", "🦁"]

if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
if "undo_cache" not in st.session_state:
    st.session_state["undo_cache"] = None
if "ai_english_answer" not in st.session_state:
    st.session_state["ai_english_answer"] = ""
if "ai_feedback_answer" not in st.session_state:
    st.session_state["ai_feedback_answer"] = ""

# -------------------------- 2. 核心工具函数 --------------------------
def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        return r.json().get("tenant_access_token")
    except Exception as e:
        print(f"获取token失败:{e}")
        return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token:
        return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        if not items:
            return pd.DataFrame()
        data = []
        for item in items:
            f = item["fields"]
            f["record_id"] = item["record_id"]
            data.append(f)
        return pd.DataFrame(data)
    except Exception as e:
        print(f"拉取数据异常:{e}")
        return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    forbidden = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt", "dt_obj", "统计课型", "序号", "总课时(h)", "上课日期", "日期文字"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden}
    payload = {"fields": clean_f}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        resp = r.json()
        print(f"【新增记录完整API返回】{resp}")
        return resp
    except Exception as e:
        print(f"新增记录异常:{e}")
        return {"code": -1}

def update_feishu_record(table_id, record_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.put(url, headers=headers, json={"fields": fields}, timeout=12)
        return r.json()
    except:
        return {"code": -1}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers, timeout=12)
        resp = r.json()
        print(f"【删除记录API返回】{resp}")
        return resp
    except Exception as e:
        print(f"删除异常:{e}")
        return {"code":-1}

# ========= 单价逻辑 =========
def get_unit_price(content):
    s = str(content).strip()
    if s in ["初中阅读","初中语法"]:
        return 45
    if s in ["高中阅读","高中完型","长难句","雅思","托福","四六级"]:
        return 50
    if s in ["单词", "大学单词", "雅思单词", "小学阅读", "旧数据补录"]:
        return 40
    return 40

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦"

def execute_undo():
    cache = st.session_state.get("undo_cache")
    if not (isinstance(cache, dict) and "action" in cache):
        return False, "无缓存操作"
    action = cache["action"]
    table_id = cache["table_id"]
    record_id = cache.get("record_id")
    origin_fields = cache.get("origin_fields")
    forbidden_undo_keys = ["record_id","dt_obj","月份","日期文字","小计","单价","统计课型","序号"]
    if origin_fields:
        origin_fields = {k:v for k,v in origin_fields.items() if k not in forbidden_undo_keys}
    if action == "add":
        if not record_id:
            return False, "add操作无record_id"
        res = delete_feishu_record(table_id, record_id)
        if res.get("code") ==0:
            return True, "撤销新增成功，已删除记录"
        else:
            return False, f"删除失败:{res}"
    elif action == "delete":
        if not origin_fields:
            return False, "delete操作缺少原始字段"
        res = add_feishu_record(table_id, origin_fields)
        if res.get("code") ==0:
            return True, "撤销删除成功，已恢复记录"
        else:
            return False, f"恢复新增失败:{res}"
    return False, "未知操作类型"

# ========= 免费英语教学 AI 接口调用 =========
def call_english_teaching_ai(system_prompt, user_prompt):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    endpoints = []
    try:
        custom_key = st.secrets.get("AI_API_KEY", "")
        custom_url = st.secrets.get("AI_BASE_URL", "")
        custom_model = st.secrets.get("AI_MODEL", "glm-4-flash")
        if custom_key and custom_url:
            endpoints.append({
                "name": "Secrets自定义接口",
                "url": custom_url,
                "model": custom_model,
                "key": custom_key,
            })
    except Exception:
        pass

    endpoints.extend([
        {
            "name": "Kilo Free Gateway",
            "url": "https://api.kilo.ai/api/gateway/chat/completions",
            "model": "kilo-auto/free",
            "key": "",
        },
        {
            "name": "LLM7 Free API",
            "url": "https://api.llm7.io/v1/chat/completions",
            "model": "gpt-3.5-turbo",
            "key": "",
        },
    ])

    errors = []
    for ep in endpoints:
        headers = {"Content-Type": "application/json"}
        if ep["key"]:
            headers["Authorization"] = f"Bearer {ep['key']}"
        payload = {
            "model": ep["model"],
            "messages": messages,
            "temperature": 0.7,
        }
        try:
            resp = requests.post(ep["url"], headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices and choices[0].get("message", {}).get("content"):
                    return True, choices[0]["message"]["content"].strip(), ep["name"]
                errors.append(f"{ep['name']}: 返回格式异常")
            else:
                errors.append(f"{ep['name']} (HTTP {resp.status_code})")
        except Exception as e:
            errors.append(f"{ep['name']}: {str(e)}")

    return False, "免费AI通道暂时繁忙，请稍后再试。\n详情：" + "；".join(errors), None

# -------------------------- 3. 全局页面样式 --------------------------
st.set_page_config(page_title="FishTeacher", layout="wide", page_icon="🐟")
st.markdown("""
<style>
.block-container {
    max-width: 1400px !important;
    padding-top: 1rem !important;
    padding-left:2rem;
    padding-right:2rem;
}
@media (max-width: 768px) {
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
}
div.stButton > button {
    width: 330px !important;
    height: 100px !important;
    margin: 0 auto 15px auto !important;
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
div.stButton > button:active {
    background-color: #5289f7 !important;
}
.brand-title {
    font-size: 32px;
    font-weight: bold;
    text-align: center;
    margin-bottom: 10px;
}
.brand-desc {
    font-size: 10px;
    color:#666666;
    text-align: center;
    margin-bottom: 15px;
}
footer {visibility: hidden;}
div[data-testid="stDataFrame"] {
    background-color: #ffffff !important;
}
div[data-testid="stDataFrame"] table {
    background-color: #ffffff !important;
}
div[data-testid="stDataFrame"] th {
    background-color: #f7f9fc !important;
    color: #000000 !important;
}
div[data-testid="stDataFrame"] td {
    background-color: #ffffff !important;
    color: #000000 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-desc">掌上拇指便捷管理</p>', unsafe_allow_html=True)

def back_home():
    st.session_state['menu_choice'] = "首页"
    st.rerun()

# --- 首页菜单 ---
if st.session_state['menu_choice'] == "首页":
    st.markdown("# 🐟 FishTeacher")
    st.markdown("掌上拇指便捷管理")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 复习提醒"): st.session_state['menu_choice'] = "提醒"; st.rerun()
        if st.button("📊 账目&明细"): st.session_state['menu_choice'] = "account"; st.rerun()
        if st.button("👥 学生档案"): st.session_state['menu_choice'] = "名册"; st.rerun()
        if st.button("🗣️ 课堂英语话术"): st.session_state['menu_choice'] = "english_talk"; st.rerun()
    with col2:
        if st.button("📝 快速录课"): st.session_state['menu_choice'] = "录入"; st.rerun()
        if st.button("📄 导出21天"): st.session_state['menu_choice'] = "导出"; st.rerun()
        if st.button("📥 批量数据导入"): st.session_state['menu_choice'] = "导入"; st.rerun()
        if st.button("📖单词带背流程"): st.session_state['menu_choice'] = "wordflow"; st.rerun()

# --- 复习提醒模块 ---
elif st.session_state['menu_choice'] == "提醒":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("🔍复习提醒")
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
                    if target_s != "全部学生" and n != target_s:
                        continue
                    if n not in reminders:
                        reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else:
            st.info("今日该学生无复习任务")

# --- 账目&明细 ---
elif st.session_state['menu_choice'] == "account":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("📊账目&明细")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if r_df.empty:
        st.info("暂无上课记录")
    else:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        r_df['日期文字'] = r_df['dt_obj'].dt.strftime('%Y-%m-%d')
        target_m = st.selectbox("📅 选择月份", sorted(r_df['月份'].unique(), reverse=True))
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时'], errors="coerce").fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']

        col_metric_1, col_metric_2 = st.columns(2)
        with col_metric_1:
            st.metric("💰 本月总薪资", f"¥{m_df['小计'].sum():,.0f}")
        with col_metric_2:
            st.metric("⌛ 本月总课时", f"{m_df['课时'].sum():.1f} h")

        st.markdown("**📊 按单价合并统计**")
        price_group = m_df.groupby("单价").agg(
            总课时=("课时", "sum"),
            总金额=("小计", "sum"),
            包含课型=("学习内容", lambda x: "、".join(sorted(set(x.tolist()))))
        ).reset_index()
        price_group = price_group.sort_values("单价", ascending=False)
        price_group = price_group[["单价", "包含课型", "总课时", "总金额"]]
        st.dataframe(price_group, use_container_width=True, hide_index=True)

        st.divider()
        col_stat, col_log = st.columns([5,5])
        with col_stat:
            st.subheader("📋 学生月度统计")
            def merge_course_name(c):
                if c in ["单词", "旧数据补录", "大学单词", "雅思单词"]:
                    return "单词课(合并)"
                return c
            m_df['统计课型'] = m_df['学习内容'].apply(merge_course_name)
            sum_df = m_df.groupby(["姓名","统计课型"]).agg({"课时":"sum","小计":"sum"}).reset_index()
            stu_total = m_df.groupby("姓名").agg({"课时":"sum","小计":"sum"}).reset_index()
            final_df = pd.merge(stu_total, sum_df[["姓名","统计课型","课时","小计"]], on="姓名", how="left")
            final_df.insert(0,"序号", range(1, len(final_df)+1))
            st.dataframe(final_df, use_container_width=True, hide_index=True, height=340)

            st.markdown("---")
            sel_stu = st.selectbox("🔍 选择学生查看当月明细", ["请选择"] + sorted(m_df["姓名"].unique()))
            if sel_stu != "请选择":
                detail_df = m_df[m_df["姓名"] == sel_stu].sort_values("日期文字", ascending=False)
                st.dataframe(detail_df[["日期文字","学习内容","课时","单价","小计"]], use_container_width=True, hide_index=True)
        with col_log:
            st.subheader("📜 全部流水记录")
            st.dataframe(m_df[["姓名","日期文字","学习内容","课时","单价","小计"]], use_container_width=True, hide_index=True, height=400)
            st.divider()
            tab_del, tab_edit = st.tabs(["🗑 删除上课记录","✏ 修改上课记录(日期/内容/课时)"])
            with tab_del:
                del_row = None
                del_sel_stu = st.selectbox("1.选择学生", ["请选择"] + sorted(m_df["姓名"].unique()), key="del_acc_stu")
                if del_sel_stu != "请选择":
                    del_sub = m_df[m_df["姓名"] == del_sel_stu].sort_values("日期文字", ascending=False)
                    del_date_list = del_sub["日期文字"].tolist()
                    del_sel_date = st.selectbox("2.选择上课日期", ["请选择"] + del_date_list, key="del_acc_date")
                    if del_sel_date != "请选择":
                        del_row = del_sub[del_sub["日期文字"] == del_sel_date].iloc[0]
                        st.info(f"待删除：{del_sel_stu}｜{del_sel_date}｜{del_row['学习内容']}｜{del_row['课时']}h")
                if st.checkbox("确认删除本条记录", disabled=(del_row is None), key="chk_del_acc"):
                    if st.button("执行删除", key="btn_del_acc"):
                        st.session_state["undo_cache"] = {
                            "action":"delete",
                            "table_id":TABLE_ID_RECORDS,
                            "record_id": del_row["record_id"],
                            "origin_fields": del_row.to_dict()
                        }
                        delete_feishu_record(TABLE_ID_RECORDS, del_row["record_id"])
                        st.toast("🗑 记录已删除，下方支持撤销", icon="⚠️")
                        time.sleep(1)
                        st.rerun()
            with tab_edit:
                edit_target = None
                edit_sel_stu = st.selectbox("1.选择学生", ["请选择"] + sorted(m_df["姓名"].unique()), key="edit_acc_stu")
                if edit_sel_stu != "请选择":
                    edit_sub = m_df[m_df["姓名"] == edit_sel_stu].sort_values("日期文字", ascending=False)
                    edit_date_list = edit_sub["日期文字"].tolist()
                    edit_sel_date = st.selectbox("2.选择上课日期", ["请选择"] + edit_date_list, key="edit_acc_date")
                    if edit_sel_date != "请选择":
                        edit_target = edit_sub[edit_sub["日期文字"] == edit_sel_date].iloc[0]
                        st.info(f"当前：{edit_target['日期文字']}｜{edit_target['学习内容']}｜{edit_target['课时']} h")
                if edit_target is not None:
                    old_content = edit_target["学习内容"]
                    old_h = float(edit_target["课时"])
                    old_d = edit_target["dt_obj"].date()
                    idx_c = LEARN_CONTENTS.index(old_content) if old_content in LEARN_CONTENTS else 0
                    idx_h = HOURS_OPTIONS.index(old_h) if old_h in HOURS_OPTIONS else 1
                    new_d = st.date_input("修改上课日期", value=old_d, key="edit_acc_newdate")
                    new_c = st.selectbox("修改学习内容", LEARN_CONTENTS, index=idx_c, key="edit_acc_newcontent")
                    new_h = st.selectbox("修改课时时长", HOURS_OPTIONS, index=idx_h, key="edit_acc_newhour")
                    if st.button("💾保存修改", key="btn_save_edit_acc"):
                        all_rec = fetch_feishu_data(TABLE_ID_RECORDS)
                        dup = False
                        if not all_rec.empty:
                            all_rec["parse_dt"] = pd.to_datetime(all_rec["学习日期"], unit='ms', errors="coerce").dt.date
                            cond = (all_rec["姓名"] == edit_sel_stu) & (all_rec["parse_dt"] == new_d) & (all_rec["record_id"] != edit_target["record_id"])
                            if all_rec[cond].shape[0]>0:
                                dup=True
                        if dup:
                            st.toast(f"⚠️ {edit_sel_stu}该日期已有课程，不可重复", icon="⚠️")
                        else:
                            ts = int(datetime.datetime.combine(new_d, datetime.time()).timestamp()*1000)
                            update_feishu_record(TABLE_ID_RECORDS, edit_target["record_id"], {"学习日期":ts,"学习内容":new_c,"课时":new_h})
                            emoji = random.choice(ANIMAL_EMOJIS)
                            st.toast(f"{emoji} 修改成功", icon="✅")
                            time.sleep(1)
                            st.rerun()

        st.divider()
        st.subheader("↩️ 撤销上一步操作")
        cache_exist = isinstance(st.session_state.get("undo_cache"), dict)
        if cache_exist:
            st.success(f"✅ 存在待撤销操作：{st.session_state['undo_cache']['action']}")
        else:
            st.warning("⚠️ 无待撤销缓存")
        chk1 = st.checkbox("启用撤销操作", disabled=not cache_exist, key="chk_undo_acc1")
        chk2 = st.checkbox("确认执行撤销", disabled=not chk1, key="chk_undo_acc2")
        if st.button("✅执行撤销", disabled=not chk2):
            ok, msg = execute_undo()
            if ok:
                st.toast(f"✅{msg}", icon="✅")
            else:
                st.toast(f"❌{msg}", icon="❌")
            st.session_state["undo_cache"] = None
            time.sleep(0.8)
            st.rerun()

# --- 快速录课 (已集成：录课时自动扣除学生档案中的剩余课时) ---
elif st.session_state['menu_choice'] == "录入":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("📝快速录课")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()) if not s_df.empty else []
    st.subheader("📝 新增录课")
    with st.form("in"):
        name = st.selectbox("学生姓名", active_s)
        date = st.date_input("上课日期")
        content = st.selectbox("内容", LEARN_CONTENTS)
        hour = st.selectbox("课时", HOURS_OPTIONS, index=1)
        submit = st.form_submit_button("确认录入")
        if submit:
            real_time_record_df = fetch_feishu_data(TABLE_ID_RECORDS)
            duplicate = False
            if not real_time_record_df.empty:
                real_time_record_df["parse_date"] = pd.to_datetime(real_time_record_df["学习日期"], unit='ms', errors='coerce').dt.date
                filter_cond = (real_time_record_df["姓名"] == name) & (real_time_record_df["parse_date"] == date)
                if real_time_record_df[filter_cond].shape[0] > 0:
                    duplicate = True
            if duplicate:
                st.toast(f"⚠️ 重复录入：{name} 在 {date} 已经存在一节课！同一天只能录入1节课", icon="⚠️")
            else:
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                new_fields = {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour}
                resp = add_feishu_record(TABLE_ID_RECORDS, new_fields)
                if resp.get("code") != 0:
                    st.toast(f"❌ 录入接口报错：{resp.get('msg','未知错误')}", icon="❌")
                else:
                    # 自动扣除学生档案中的剩余课时
                    stu_row = s_df[s_df['姓名'] == name]
                    if not stu_row.empty:
                        s_record_id = stu_row.iloc[0]['record_id']
                        current_remain = float(stu_row.iloc[0].get('剩余课时', 0) or 0)
                        new_remain = max(0.0, current_remain - float(hour))
                        update_feishu_record(TABLE_ID_STUDENTS, s_record_id, {"剩余课时": new_remain})

                    emoji = random.choice(ANIMAL_EMOJIS)
                    st.toast(f"{emoji} 同步成功！已自动扣除 {name} 课时 {hour}h (剩余: {new_remain}h)", icon="✅")
                    time.sleep(1.2); st.rerun()

    st.divider()
    st.subheader("✏️ 修改上课记录")
    r_df_edit = fetch_feishu_data(TABLE_ID_RECORDS)
    if r_df_edit.empty:
        st.info("暂无上课记录")
    else:
        r_df_edit['dt_obj'] = pd.to_datetime(r_df_edit['学习日期'], unit='ms', errors='coerce')
        r_df_edit['日期文字'] = r_df_edit['dt_obj'].dt.strftime('%Y-%m-%d')
        edit_target = None
        e_stu = st.selectbox("1.选择学生", ["请选择学生"] + sorted(r_df_edit['姓名'].unique().tolist()), key="edit_in_stu")
        if e_stu != "请选择学生":
            e_stu_rec = r_df_edit[r_df_edit["姓名"] == e_stu].sort_values("日期文字", ascending=False)
            e_date_opt = e_stu_rec["日期文字"].tolist()
            e_date_sel = st.selectbox("2.选择上课日期", ["请选择日期"] + e_date_opt, key="edit_in_date")
            if e_date_sel != "请选择日期":
                edit_target = r_df_edit[(r_df_edit["姓名"] == e_stu) & (r_df_edit["日期文字"] == e_date_sel)].iloc[0]
                st.info(f"当前：{edit_target['日期文字']}｜{edit_target['学习内容']}｜{edit_target['课时']} h")
        if edit_target is not None:
            old_c = edit_target["学习内容"]
            old_h = float(edit_target["课时"])
            old_d = edit_target["dt_obj"].date()
            idx_c = LEARN_CONTENTS.index(old_c) if old_c in LEARN_CONTENTS else 0
            idx_h = HOURS_OPTIONS.index(old_h) if old_h in HOURS_OPTIONS else 1
            new_d = st.date_input("修改上课日期", value=old_d, key="edit_in_newdate")
            new_c = st.selectbox("修改学习内容", LEARN_CONTENTS, index=idx_c, key="edit_in_content")
            new_h = st.selectbox("修改课时时长", HOURS_OPTIONS, index=idx_h, key="edit_in_hour")
            if st.button("💾 保存修改", key="btn_save_edit_in"):
                ts = int(datetime.datetime.combine(new_d, datetime.time()).timestamp() * 1000)
                update_fields = {"学习日期": ts, "学习内容": new_c, "课时": new_h}
                resp = update_feishu_record(TABLE_ID_RECORDS, edit_target["record_id"], update_fields)
                if resp.get("code") == 0:
                    # 同步更正课时差值
                    diff_h = new_h - old_h
                    if diff_h != 0 and not s_df.empty:
                        s_row = s_df[s_df['姓名'] == e_stu]
                        if not s_row.empty:
                            s_rid = s_row.iloc[0]['record_id']
                            cur_rem = float(s_row.iloc[0].get('剩余课时', 0) or 0)
                            update_feishu_record(TABLE_ID_STUDENTS, s_rid, {"剩余课时": max(0.0, cur_rem - diff_h)})
                    emoji = random.choice(ANIMAL_EMOJIS)
                    st.toast(f"{emoji} 修改成功！课时已联动更新", icon="✅")
                    time.sleep(1); st.rerun()
                else:
                    st.toast("❌ 修改失败", icon="❌")

# --- 学生档案 (带剩余总课时记录、自动扣除、充值与消费明细) ---
elif st.session_state['menu_choice'] == "名册":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("👥 学生档案 & 课时管理")
    
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    r_df_all = fetch_feishu_data(TABLE_ID_RECORDS)

    with st.expander("➕ 添加新学员（支持初始剩余课时）", expanded=False):
        with st.form("add_stu_form"):
            n = st.text_input("姓名")
            grade = st.selectbox("年级", GRADE_OPTIONS)
            s_status = st.selectbox("状态", STATUS_OPTIONS)
            init_hours = st.number_input("初始总剩余课时 (h)", min_value=0.0, max_value=200.0, value=0.0, step=0.5)
            info = st.text_area("基础档案信息")
            if st.form_submit_button("确认入库"):
                if n:
                    if not s_df.empty and n in s_df['姓名'].tolist():
                        st.toast(f"⚠️ 学生【{n}】档案已存在！", icon="⚠️")
                    else:
                        new_stu_fields = {"姓名": n, "年级": grade, "状态": s_status, "剩余课时": init_hours, "基础信息": info}
                        resp = add_feishu_record(TABLE_ID_STUDENTS, new_stu_fields)
                        record_id = resp.get("data",{}).get("record_id")
                        st.session_state["undo_cache"] = {
                            "action":"add","table_id":TABLE_ID_STUDENTS,
                            "record_id": record_id,"origin_fields": new_stu_fields
                        }
                        emoji = random.choice(ANIMAL_EMOJIS)
                        st.toast(f"{emoji} 学员入库成功！初始课时：{init_hours}h", icon="✅")
                        time.sleep(1); st.rerun()

    if not s_df.empty:
        st.divider()
        st.subheader("📂 编辑/查看学生档案 & 课时充值扣除")
        ts = st.selectbox("选择学生姓名", ["未选择"] + sorted(s_df['姓名'].tolist()))
        if ts != "未选择":
            data = s_df[s_df['姓名'] == ts].iloc[0]
            with st.container(border=True):
                current_grade = data.get("年级", "未填写")
                idx_g = GRADE_OPTIONS.index(current_grade) if current_grade in GRADE_OPTIONS else 0
                
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    ng = st.selectbox("年级", GRADE_OPTIONS, index=idx_g, key="edit_stu_grade")
                    ns = st.selectbox("状态", STATUS_OPTIONS, index=STATUS_OPTIONS.index(data['状态']) if data['状态'] in STATUS_OPTIONS else 0, key="edit_stu_status")
                with col_info2:
                    current_rem = float(data.get("剩余课时", 0) or 0)
                    st.metric("⏳ 当前剩余课时", f"{current_rem:.1f} h")
                    # 快捷充值/扣减组件
                    adjust_h = st.number_input("快捷充值(+) / 手动扣除(-) 课时", min_value=-50.0, max_value=50.0, value=0.0, step=0.5, key="adjust_hours_num")

                ni = st.text_area("基础档案信息 / 备注", value=data.get('基础信息', ""), height=150, key="edit_stu_info")
                
                c1, c2 = st.columns(2)
                if c1.button("💾 保存档案内容及课时调整"):
                    final_rem = max(0.0, current_rem + adjust_h)
                    update_feishu_record(TABLE_ID_STUDENTS, data['record_id'], {
                        "年级": ng, 
                        "状态": ns, 
                        "剩余课时": final_rem, 
                        "基础信息": ni
                    })
                    emoji = random.choice(ANIMAL_EMOJIS)
                    st.toast(f"{emoji} 档案已更新！当前剩余课时：{final_rem}h", icon="✅")
                    time.sleep(1); st.rerun()
                if c2.button("🗑️ 彻底删除该学生档案"):
                    if st.checkbox("确认彻底删除"):
                        st.session_state["undo_cache"] = {
                            "action":"delete","table_id":TABLE_ID_STUDENTS,
                            "record_id":data["record_id"],"origin_fields": data.to_dict()
                        }
                        delete_feishu_record(TABLE_ID_STUDENTS, data['record_id'])
                        st.toast("⚠️ 学员已删除", icon="⚠️")
                        time.sleep(1); st.rerun()

            # 展示该学生的上课与课时消耗流水明细
            st.markdown(f"#### 📜 {ts} 的上课及扣课流水明细")
            if not r_df_all.empty and '姓名' in r_df_all.columns:
                stu_records = r_df_all[r_df_all['姓名'] == ts].copy()
                if not stu_records.empty:
                    stu_records['dt_obj'] = pd.to_datetime(stu_records['学习日期'], unit='ms', errors='coerce')
                    stu_records['上课日期'] = stu_records['dt_obj'].dt.strftime('%Y-%m-%d')
                    stu_records = stu_records.sort_values("上课日期", ascending=False)
                    st.dataframe(stu_records[["上课日期", "学习内容", "课时"]], use_container_width=True, hide_index=True)
                else:
                    st.info("该学员暂无上课打卡记录")

    st.divider()
    st.subheader("↩️ 撤销上一步操作")
    cache_exist = isinstance(st.session_state.get("undo_cache"), dict)
    if cache_exist:
        st.success(f"✅ 当前可撤销：{st.session_state['undo_cache']['action']}")
    else:
        st.warning("⚠️ 暂无待撤销操作")
    chk_undo_enable = st.checkbox("启用撤销操作", disabled=not cache_exist, key="chk_undo_enable_stu")
    chk_undo_confirm = st.checkbox("确认执行撤销", disabled=not chk_undo_enable, key="chk_undo_confirm_stu")
    if st.button("✅ 执行撤销", disabled= not (chk_undo_enable and chk_undo_confirm)):
        ok, msg = execute_undo()
        if ok:
            st.toast(f"✅ {msg}", icon="✅")
        else:
            st.toast(f"❌ {msg}", icon="❌")
        st.session_state["undo_cache"] = None
        time.sleep(0.8); st.rerun()

# --- 导出21天表 + 本月课时表格 ---
elif st.session_state['menu_choice'] == "导出":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("📄导出功能")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    stu_df_all = fetch_feishu_data(TABLE_ID_STUDENTS)
    stu_grade_map = dict()
    stu_status_map = dict()
    if not stu_df_all.empty:
        for _,row in stu_df_all.iterrows():
            stu_grade_map[row["姓名"]] = row.get("年级","未填写")
            stu_status_map[row["姓名"]] = row.get("状态","")
    if r_all.empty:
        st.info("暂无上课记录，无法导出")
    else:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        r_all['ym_str'] = r_all['dt'].apply(lambda x:x.strftime("%Y-%m") if pd.notna(x) else None)
        tab1, tab2 = st.tabs(["📄 导出21天抗遗忘表","📊 导出本月课时表格(行学生，列日期)"])
        with tab1:
            target = st.selectbox("学员", sorted(r_all['姓名'].unique().tolist()))
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            preview_df = pd.DataFrame(output[2:])
            st.subheader("👁️ 表格预览")
            st.dataframe(preview_df, use_container_width=True, hide_index=True, height=350)
            if st.button("生成21天表格"):
                buf = io.StringIO()
                pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
                st.download_button(f"📥 下载 {target}_21天表.csv", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")
                emoji = random.choice(ANIMAL_EMOJIS)
                st.toast(f"{emoji} 21天表格已生成，请下载", icon="✅")
        with tab2:
            ym_list = sorted([x for x in r_all['ym_str'].unique() if x is not None], reverse=True)
            sel_month = st.selectbox("选择要导出的月份", ym_list)
            df_month = r_all[r_all['ym_str'] == sel_month].copy()
            df_month["date_short"] = df_month["dt"].apply(lambda d:d.strftime("%m.%d"))
            stu_date_h = defaultdict(lambda:defaultdict(float))
            stu_total = defaultdict(float)
            all_dates = set()
            all_stus = set()
            for _,row in df_month.iterrows():
                sname = row["姓名"]
                dshort = row["date_short"]
                h = float(row["课时"])
                stu_date_h[sname][dshort] += h
                stu_total[sname] += h
                all_dates.add(dshort)
                all_stus.add(sname)
            sorted_stu = sorted(all_stus)
            sorted_date = sorted(all_dates, key=lambda x:(int(x.split(".")[0]), int(x.split(".")[1])))
            def display_name(s):
                stat = stu_status_map.get(s, "")
                if stat == "结课/毕业":
                    return f"{s}(结课)"
                elif stat == "更换教练":
                    return f"{s}(更换教练)"
                elif stat == "停课/休假":
                    return f"{s}(停课)"
                return s
            csv_rows = []
            header_row = ["姓名","年级","总课时"] + sorted_date
            csv_rows.append(header_row)
            for s in sorted_stu:
                row_data = [display_name(s), stu_grade_map.get(s,"未填写"), round(stu_total[s],1)]
                for d in sorted_date:
                    row_data.append(round(stu_date_h[s].get(d,0.0),1))
                csv_rows.append(row_data)
            st.subheader("👁️ 课时矩阵预览")
            preview_matrix = pd.DataFrame(csv_rows[1:], columns=csv_rows[0])
            st.dataframe(preview_matrix, use_container_width=True, hide_index=True, height=380)
            if st.button("生成课时矩阵表格"):
                buf2 = io.StringIO()
                pd.DataFrame(csv_rows).to_csv(buf2, index=False, header=False, encoding="utf-8-sig")
                filename = f"{sel_month}_课时矩阵表_含年级.csv"
                st.download_button(f"📥 下载 {filename}", buf2.getvalue().encode("utf-8-sig"), filename, "text/csv")
                emoji = random.choice(ANIMAL_EMOJIS)
                st.toast(f"{emoji} 课时矩阵表格已生成，请下载", icon="✅")

# --- 批量导入 ---
elif st.session_state['menu_choice'] == "导入":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("📥批量数据导入")
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f)
        bar = st.progress(0)
        if st.button("启动同步"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS)
            names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                grade_val = str(row.get("年级","未填写")) if "年级" in df.columns else "未填写"
                if name not in names_in:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "年级":grade_val, "状态": "在读/上课", "剩余课时": 0.0})
                    names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except:
                    pass
                bar.progress((i+1)/len(df))
            emoji = random.choice(ANIMAL_EMOJIS)
            st.toast(f"{emoji} 批量导入完成", icon="✅")
            time.sleep(1.2); st.rerun()

# ====================== 单词带背流程页面 ======================
elif st.session_state['menu_choice'] == "wordflow":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("📖 单词训练带背完整流程")
    st.markdown("> 上课对照流程，可上传原始流程示意图")
    upload_img = st.file_uploader("上传单词训练流程照片", type=["png","jpg","jpeg"])
    if upload_img is not None:
        st.image(upload_img, use_container_width=True)
    st.divider()
    st.subheader("一、跟读带读环节")
    st.markdown("""
1. 教练正常速度带读1遍英文，学生跟读1遍英文
2. 教练快速有节奏带读3遍英文，学生快速跟读3遍英文
3. 教练带读1遍英文(同时点击空白显示中文)，学生跟读英+中；快速带读2英+1中，学生跟读2英+1中
4. 教练读英文，用手挡住英文，学生说出1遍英文+1遍中文
""")
    st.subheader("二、上去下来学新｜向上复习旧单词，往下学习新单词")
    st.markdown("""
>以1组5个单词为示例：**学1→学2→复1、2→学3→复2、1、2、3→学4→复3、2、1、2、3、4→学5**
""")
    st.subheader("三、五上三下二上（学到第5个单词的复习逻辑）")
    st.markdown("**54345，212**：从第五个往上复习到第三个单词，再下回到第五个单词；再从第二个单词往上复习，再回到第二个")
    st.subheader("四、总复习（1‑5，5‑1）")
    st.markdown("能多快有多快；教练点击单词空白带读英文，学生说出英文+中文")
    st.subheader("五、听音识单词（1‑5，5‑1）")
    st.markdown("学生闭上眼睛，播放单词发音，学生说出英文和中文，**教练不带读**")
    st.subheader("六、模拟剪纸条（2分钟完成，动作流畅快速）")
    st.markdown("""
学生说出一两个字的时候，就准备下一个单词，加快衔接速度。
>📝备注：遇到学生不熟悉的单词：教练带读2遍英文 +1遍中文，同时点击空白显示中文
🔁循环规则
- **组内循环**：5个单词为一组，本组全部学完，单词剪给学生
- **组组循环**：学完第2组，第1+2组合并；学完第3组，1+2+3组合并
- **章循环**：9组合计45个单词全部学完，全部混组，一整章单词给到学生
""")
    st.subheader("七、学后检测")
    st.markdown("""
全部打勾，学生快速说出英文+中文。
遇到不熟悉、翻译错误单词：点出中文，带读两遍英文一遍中文。
> ⚠️重点：学后检测依旧不熟 = 没有掌握，需要记录后台重新学习。
""")
    st.divider()
    
    st.subheader("📌 课堂反馈评语（快捷模板 & AI 定制）")
    
    with st.expander("📋 常用快捷评语模板（点击展开直接复制）", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.code("本节课新词学习效率高，复习检测也没有遗忘，能力很强。", language=None)
            st.code("复习整体掌握扎实，原有能力保持稳定，继续坚持巩固。", language=None)
        with c2:
            st.code("本节课复习反馈良好，已学内容无明显遗忘，维持现有节奏稳步积累。", language=None)
            st.code("部分单词熟练度不足，标记待复习，后续课堂重点复盘巩固。", language=None)

    st.markdown("#### ✨ AI 专属课堂反馈与复习总结")
    s_df_fb = fetch_feishu_data(TABLE_ID_STUDENTS)
    stu_opts = ["(不指定/手动填写)"]
    if not s_df_fb.empty and '状态' in s_df_fb.columns:
        stu_opts += sorted(s_df_fb[s_df_fb['状态'] == "在读/上课"]['姓名'].tolist())

    with st.form("ai_class_feedback_form"):
        col_fb1, col_fb2 = st.columns(2)
        with col_fb1:
            fb_stu = st.selectbox("选择学员", stu_opts)
            fb_content = st.selectbox("本节学习内容", LEARN_CONTENTS)
        with col_fb2:
            fb_perf = st.selectbox(
                "课堂及复习整体表现",
                [
                    "新词吸收快，旧词复习零遗忘，状态极佳",
                    "整体掌握扎实，个别难点词经带读后已攻克",
                    "专注度不错，但部分易混词/拼写熟练度还需巩固",
                    "复习环节有些生疏，课后需要重点按21天节奏复盘",
                    "首次上课/新阶段起步，适应良好，潜力很大"
                ]
            )
            fb_tone = st.selectbox("发送对象/语气侧重", ["发给家长（全面专业+暖心肯定）", "发给学生本人（亲切鼓励+明确行动点）"])

        fb_note = st.text_input(
            "补充细节（可选）",
            placeholder="例如：今天背了45个词；abandon 和 aboard 容易混；听音识词反应特别快"
        )
        fb_submit = st.form_submit_button("🌟 生成专属反馈评语")

    if fb_submit:
        stu_name_str = "同学" if fb_stu == "(不指定/手动填写)" else f"{fb_stu}同学"
        sys_prompt_fb = (
            "你是一位说话特别好听、温润真诚、高情商且专业全面的英语带背教练老师。"
            "你非常擅长写微信课堂反馈与复习总结，既能让家长/学生感受到被看见、被真诚鼓励，又能把学习复盘和复习重点交代得清清楚楚。"
            "请按以下结构自然分段输出（不要使用死板的Markdown标题符号如###，适合直接复制发微信，适当点缀1-3个得体的emoji）：\n"
            "1. 【课堂亮点与肯定】：真诚具体地夸奖孩子的专注度、反应速度或学习状态；\n"
            "2. 【学习与复习复盘】：清晰总结本节课的新学内容与旧词复习检测情况，若有薄弱点，用温和、充满信心的语气指出；\n"
            "3. 【课后复习建议与寄语】：结合21天抗遗忘规律给出简单可执行的复习叮嘱，并以充满能量和期待的鼓励收尾。\n"
            "要求：语言流畅自然、不啰嗦、不说教，字数控制在150~260字左右，可直接复制发送。"
        )
        user_prompt_fb = (
            f"学员：{stu_name_str}\n"
            f"本节学习内容：{fb_content}\n"
            f"课堂及复习表现：{fb_perf}\n"
            f"发送对象：{fb_tone}\n"
            f"老师补充细节：{fb_note if fb_note.strip() else '无额外补充，请结合表现自然发挥'}"
        )
        with st.spinner("✨ 正在组织高情商评语..."):
            ok, ans, _ = call_english_teaching_ai(sys_prompt_fb, user_prompt_fb)
        if ok:
            st.session_state["ai_feedback_answer"] = ans
        else:
            st.error(ans)

    if st.session_state.get("ai_feedback_answer"):
        st.success("✅ 生成完成，点击右上角即可一键复制：")
        st.code(st.session_state["ai_feedback_answer"], language=None)

# ====================== 课堂英语话术 + 免费英语教学 AI 助手 ======================
elif st.session_state['menu_choice'] == "english_talk":
    if st.button("🏠 返回主菜单"): back_home()
    st.header("🗣️ 课堂英语话术")
    st.markdown("### 英语课堂口语小抄（中英对照｜直接复制）")
    st.markdown("""
## 一、课程开场 & 流程指令

1. Class begins. 上课。
2. Let’s start our review! 开始复习罗！
3. Now let’s learn something new. 现在进入学新。
4. Try it on your own. 自己来一遍。
5. Sorry, I clicked the wrong option. 不好意思，我点错了选项。
6. Let’s have a pre-class check. 学前检测一下。
7. Let’s have a post-class check. 学后检测一下。
8. Today is a review class. 今天是复习课。
9. Class is over. 下课。
10. Let’s begin our class. 我们开始上课。

## 二、控场引导

1. It’s your turn. 轮到你了。
2. Read it again. 再读一遍。
3. Take your time. 别急，慢慢来。
4. Listen carefully. 仔细听。
5. Read after me. 跟着我读。
6. Speak louder. 大声一点。
7. Look here. 看这里。
8. Are you ready? 准备好了吗？
9. Pause for a second. 停一下。
10. Let’s do it together. 我们一起。
11. Who wants to have a try? 谁想来试试？
12. You may sit down. 可以坐下了。

## 三、切换小组 / 切换板块

1. Good reading! Next group. 读得不错，我们下一组。
2. Nice job! Let’s move on to the next group. 很棒！我们换到下一组。
3. Well done! Next group, please. 做得很好，请下一组。
4. Let’s quickly move on to the next part. 让我们快速进入下一部分学习。
5. Let’s quickly go to the next group. 我们快速来到下一组（学生小组）。

## 四、夸奖｜读得不错（轮换用）

1. Good reading! 读得很好！
2. Nice pronunciation. 发音不错。
3. That sounds great. 听起来很棒。
4. You read it smoothly. 你读得很流畅。
5. Perfect! 非常好！
6. Excellent! 太棒啦！
7. Nice work! 做得很好。
8. I love your reading. 我很喜欢你的朗读。
9. That’s close. 差不多了。

## 五、安慰、重试、跳过延后复习

1. It’s okay. Let’s read it a few more times. 没事的，我们再多念几遍。
2. Don’t worry. We can practise it again. 别担心，我们可以再练练。
3. No problem. Let’s try once more slowly. 没关系，我们慢一点再来一次。
4. Just take it easy. 放轻松就好。
5. It’s fine to make mistakes. 犯错没关系。
6. Mistakes help us learn. 错误帮助我们学习。
7. Let’s skip this one for now. We’ll review it later. 我们先跳过这个，之后再来复习。
8. We can leave this here. We will go over it after class. 先放一放，课下我们再复习。
9. Don’t worry, we will come back to this next time. 不用担心，下次我们回头再学这个。
10. Try again. 再试一次。

## 六、配套话题句（口语问答）

1. meet sb 和某人见面 / 见一面
2. meet up with sb （约好）和某人碰面
3. I want to meet her. 我想和她见一面。
4. I’ll meet up with my friend. 我要和朋友见一面。
5. I need to see him. 我要跟他见一面。
6. Looking forward to seeing you. 期待见到你（认识的人）。
7. Looking forward to meeting you. 期待和你见面（初次）。
8. Can’t wait to see you. 迫不及待想见你。
9. I’m looking forward to our meeting. 我期待我们见面。
10. What are your hobbies? 你的爱好是什么？
11. And my hobbies are writing, listening to music, painting and photography, mostly!!  
    我的爱好主要是写作、听音乐、画画还有摄影！
12. Who do you want to meet up with this weekend?  
    这周末你想和谁见一面？
""")

    st.divider()
    st.subheader("🤖 英语教学 AI 助手")
    with st.form("english_ai_mini"):
        ai_q = st.text_input(
            "输入教学要求",
            placeholder="例如：给初二学生讲解 abandon 的记忆法和2个例句 / 学生走神怎么用英语提醒",
        )
        ai_go = st.form_submit_button("✨ 生成答案")

    if ai_go:
        if not ai_q.strip():
            st.toast("⚠️ 请输入要求", icon="⚠️")
        else:
            sys_prompt = (
                "你是一位专业的中国英语教学教练AI助手，擅长21天抗遗忘单词带背、中小学及大学英语教学。"
                "请根据老师输入的教学要求，直接给出简洁、实用、可直接用于课堂或发给学生/家长的答案"
                "（如单词助记与例句、中英课堂话术、通俗语法拆解、学情反馈等），不要废话，排版精简清晰。"
            )
            with st.spinner("🤖 生成中..."):
                ok, ans, _ = call_english_teaching_ai(sys_prompt, ai_q.strip())
            if ok:
                st.session_state["ai_english_answer"] = ans
            else:
                st.error(ans)

    if st.session_state.get("ai_english_answer"):
        with st.container(border=True):
            st.markdown(st.session_state["ai_english_answer"])
