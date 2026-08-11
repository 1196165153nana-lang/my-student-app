# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time

# -------------------------- 页面全局配置 --------------------------
st.set_page_config(page_title="FishTeacher", layout="centered", page_icon="🐟")

# 全局样式CSS
st.markdown("""
    <style>
    /* 1. 限制电脑端最大宽度 */
    .block-container { max-width: 850px !important; padding-top: 1rem !important; }
    
    /* 2. 响应式列宽：手机端自动变一列并撑满 */
    @media (max-width: 600px) {
        [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
    }

    /* 3. 蓝色边框长方形按钮样式 */
    div.stButton > button {
        width: 100% !important;
        height: 100px !important;
        border: 2px solid #4285F4 !important;
        background-color: transparent !important;
        border-radius: 12px !important;
        font-size: 18px !important;
    }
    div.stButton > button:hover {
        background-color: rgba(66,133,244,0.1) !important;
    }

    /* 下拉框放大 */
    div.stSelectbox > div > div {
        min-height: 50px !important;
        font-size: 16px !important;
    }

    /* 三级标题样式 */
    .brand-title { font-size: 36px; font-weight: bold; text-align: center; margin: 10px 0; }
    .brand-subtitle { font-size: 22px; text-align: center; color: #aaa; margin: 8px 0; }
    .brand-mini { font-size: 16px; text-align: center; color: #888; margin: 4px 0; }
    </style>
""", unsafe_allow_html=True)

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读"]
PRICE_MAP = {
    "单词": 40,
    "大学单词": 40,
    "雅思单词": 40,
    "小学阅读": 60,
    "初中阅读": 45
}

# -------------------------- 飞书多维表格API工具函数 --------------------------
def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return res.json()["tenant_access_token"]

def get_table_data(table_id):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    page_token = ""
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=100&page_token={page_token}"
        r = requests.get(url, headers=headers)
        data = r.json()["data"]
        records.extend(data["items"])
        if not data["has_more"]:
            break
        page_token = data["page_token"]
    rows = []
    for item in records:
        row = item["fields"]
        row["record_id"] = item["record_id"]
        rows.append(row)
    return pd.DataFrame(rows)

def add_feishu_record(table_id, fields):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    res = requests.post(url, headers=headers, json={"fields": fields})
    return res.json()

def delete_feishu_record(table_id, record_id):
    token = get_feishu_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    requests.delete(url, headers=headers)

# -------------------------- 初始化会话缓存 --------------------------
if "undo_cache" not in st.session_state:
    st.session_state["undo_cache"] = None

# -------------------------- 顶部标题区 --------------------------
st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-subtitle">高效学员管理 & 21天抗遗忘系统</p>', unsafe_allow_html=True)
st.divider()

# -------------------------- 侧边栏导航 --------------------------
menu = st.sidebar.radio("功能导航", ["录入课时记录", "财务课时核算", "学员档案管理"])

# -------------------------- 模块1：录入课时记录 --------------------------
if menu == "录入课时记录":
    st.subheader("📝 新增学员上课记录")
    # 加载学员列表
    student_df = get_table_data(TABLE_ID_STUDENTS)
    student_list = sorted(student_df["姓名"].unique().tolist())
    record_df = get_table_data(TABLE_ID_RECORDS)

    with st.form("add_record_form"):
        select_stu = st.selectbox("选择学员", student_list)
        select_content = st.selectbox("学习内容", LEARN_CONTENTS)
        select_hour = st.number_input("课时", min_value=0.5, max_value=4.0, step=0.5, value=0.5)
        select_date = st.date_input("上课日期", value=datetime.date.today())
        submit_btn = st.form_submit_button("提交本节课记录")

        if submit_btn:
            date_str = select_date.strftime("%Y-%m-%d")
            # 校验：同一学生同一天仅允许一条记录
            repeat_check = record_df[(record_df["姓名"] == select_stu) & (record_df["日期文字"] == date_str)]
            if len(repeat_check) > 0:
                st.error(f"❌ {select_stu} 在 {date_str} 已有课时记录，禁止重复录入！")
            else:
                add_fields = {
                    "姓名": select_stu,
                    "学习内容": select_content,
                    "课时": select_hour,
                    "日期文字": date_str,
                    "月份": date_str[:7]
                }
                add_feishu_record(TABLE_ID_RECORDS, add_fields)
                st.success(f"✅ {select_stu} {date_str} 课时录入完成")
                time.sleep(1)
                st.rerun()

# -------------------------- 模块2：财务课时核算（完整左右分栏+两级删除选择） --------------------------
elif menu == "财务课时核算":
    st.subheader("💰 财务课时核算")
    r_df = get_table_data(TABLE_ID_RECORDS)
    if len(r_df) == 0:
        st.info("暂无课时记录")
    else:
        # 顶部筛选月份
        select_month = st.selectbox("选择核算月份", sorted(r_df["月份"].unique(), reverse=True))
        month_df = r_df[r_df["月份"] == select_month].copy()
        # 顶部汇总数据
        total_hour = month_df["课时"].sum()
        total_money = 0
        for _, row in month_df.iterrows():
            content = row["学习内容"]
            hour = row["课时"]
            price = PRICE_MAP.get(content, 45)
            total_money += price * hour
        # 顶部总指标展示
        col_top1, col_top2 = st.columns(2)
        with col_top1:
            st.metric(label="本月总课时", value=f"{total_hour} h")
        with col_top2:
            st.metric(label="本月预估薪资", value=f"{total_money} 元")

        st.divider()
        # 左右分栏：左统计 / 右流水删除
        col_stat, col_log = st.columns([1, 1.3])

        # ========== 左侧：月度统计汇总 ==========
        with col_stat:
            st.subheader("📊 月度统计")
            student_sum = month_df.groupby("姓名").agg(总课时=("课时", "sum")).reset_index()
            def calc_single_salary(name):
                sub = month_df[month_df["姓名"] == name]
                total = 0
                for _, r in sub.iterrows():
                    total += PRICE_MAP.get(r["学习内容"],45) * r["课时"]
                return total
            student_sum["单人总薪资"] = student_sum["姓名"].apply(calc_single_salary)
            st.dataframe(student_sum[["姓名", "总课时", "单人总薪资"]], use_container_width=True, hide_index=True)

        # ========== 右侧：流水明细 + 两级选择删除功能（缩进规范无报错） ==========
        with col_log:
            st.subheader("📜 全部流水记录（可删除）")
            show_df = month_df.copy()
            st.dataframe(show_df[["姓名","日期文字","学习内容","课时"]], use_container_width=True, hide_index=True, height=480)

            st.divider()
            st.subheader("🗑️ 删除上课记录")
            target_row = None
            # 第一步：选择学生
            del_student = st.selectbox("1. 选择学生", ["请选择学生"] + sorted(show_df['姓名'].unique().tolist()))
            if del_student != "请选择学生":
                # 筛选该学生当月全部上课记录，倒序展示日期
                student_records = show_df[show_df['姓名'] == del_student].sort_values("日期文字", ascending=False)
                date_list = student_records['日期文字'].tolist()
                del_date = st.selectbox("2. 选择上课日期", ["请选择日期"] + date_list)
                if del_date != "请选择日期":
                    # 匹配唯一目标行数据
                    target_row = show_df[(show_df['姓名'] == del_student) & (show_df['日期文字'] == del_date)].iloc[0]
                    st.info(f"待删除记录：{del_student} | {del_date} | {target_row['学习内容']} | {target_row['课时']}h")
            
            # 确认删除勾选框，未选完整信息时置灰不可点
            confirm_del = st.checkbox("确认要删除这条记录", disabled=(target_row is None))
            if confirm_del and st.button("执行删除", type="secondary"):
                # 缓存删除记录用于撤销功能
                st.session_state['undo_cache'] = {"table": TABLE_ID_RECORDS, "data": target_row.to_dict()}
                delete_feishu_record(TABLE_ID_RECORDS, target_row['record_id'])
                st.toast("🗑️ 记录已删除，页面即将刷新", icon="⚠️")
                time.sleep(1)
                st.rerun()

# -------------------------- 模块3：学员档案管理（添加学员默认展开、禁止重名） --------------------------
elif menu == "学员档案管理":
    st.subheader("👥 学员档案管理")
    student_df = get_table_data(TABLE_ID_STUDENTS)

    # 添加新学员（默认展开不收起）
    with st.expander("➕ 添加新学员", expanded=True):
        with st.form("add_student_form"):
            new_name = st.text_input("姓名")
            new_info = st.text_area("基础档案信息")
            sub_stu_btn = st.form_submit_button("确认入库")
            if sub_stu_btn:
                if not new_name.strip():
                    st.error("姓名不能为空")
                elif new_name in student_df["姓名"].tolist():
                    st.error(f"学员【{new_name}】已存在，禁止重复创建")
                else:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": new_name, "档案备注": new_info})
                    st.success(f"✅ 学员 {new_name} 创建完成")
                    time.sleep(1)
                    st.rerun()

    st.divider()
    st.subheader("📋 现有学员列表")
    edit_name = st.selectbox("选择学员查看/编辑", ["请选择学员"] + sorted(student_df["姓名"].unique()))
    if edit_name != "请选择学员":
        edit_row = student_df[student_df["姓名"] == edit_name].iloc[0]
        with st.form("edit_student_form"):
            edit_info = st.text_area("档案备注", value=edit_row.get("档案备注", ""))
            save_btn = st.form_submit_button("保存修改")
            if save_btn:
                token = get_feishu_token()
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID_STUDENTS}/records/{edit_row['record_id']}"
                requests.put(url, headers=headers, json={"fields": {"档案备注": edit_info}})
                st.success("档案更新成功")
                time.sleep(1)
                st.rerun()

# -------------------------- 撤销删除功能（侧边栏） --------------------------
if st.session_state["undo_cache"] is not None:
    st.sidebar.divider()
    if st.sidebar.button("↩️ 撤销上一条删除记录"):
        cache = st.session_state["undo_cache"]
        add_feishu_record(cache["table"], cache["data"])
        st.session_state["undo_cache"] = None
        st.sidebar.success("撤销完成，数据已恢复")
        time.sleep(1)
        st.rerun()
