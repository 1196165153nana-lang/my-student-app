# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import datetime
import os
import io

# -------------------------- 文件配置 --------------------------
DATA_FILE = "student_records.csv"
STUDENT_DB = "students_database.csv"

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# 初始化文件
def init_files():
    if not os.path.exists(DATA_FILE):
        pd.DataFrame(columns=["姓名", "学习日期", "学习内容", "课时"]).to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    if not os.path.exists(STUDENT_DB):
        pd.DataFrame(columns=["姓名", "状态", "备注"]).to_csv(STUDENT_DB, index=False, encoding="utf-8-sig")

init_files()

# -------------------------- 工具函数 --------------------------
def load_records():
    return pd.read_csv(DATA_FILE, encoding="utf-8-sig")

def load_students():
    return pd.read_csv(STUDENT_DB, encoding="utf-8-sig")

def save_students(df):
    df.to_csv(STUDENT_DB, index=False, encoding="utf-8-sig")

# 生成微信文案
def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_learn_dates = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_learn_dates])
    
    msg = f"""【21天抗遗忘复习提醒】

{rv_date_str}复习内容为：

{ln_dates_str}

请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]

也请家长把复习视频发到群里🌹"""
    return msg

# -------------------------- 界面配置 (自适应优化) --------------------------
st.set_page_config(
    page_title="21天抗遗忘系统", 
    layout="centered", # 手机端居中显示更美观
    page_icon="🎯"
)

# 手机端样式微调
st.markdown("""
    <style>
    /* 让按钮更大，方便手指点击 */
    .stButton > button {
        width: 100%;
        height: 3.5em;
    }
    /* 调整代码块字体，方便手机阅读 */
    code {
        font-size: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 顶部提醒 ---
r_df_check = load_records()
r_df_check['学习日期'] = pd.to_datetime(r_df_check['学习日期']).dt.date
today = datetime.date.today()
today_tasks_count = 0
for _, row in r_df_check.iterrows():
    if (today - row['学习日期']).days + 1 in REVIEW_DAYS:
        today_tasks_count += 1

if today_tasks_count > 0:
    st.error(f"🚨 **今日代办**：有 {today_tasks_count} 条复习任务待处理！")

# --- 下拉菜单导航 ---
menu = st.selectbox("📌 切换功能模块", ["🔍 复习提醒查询", "📝 录入课时记录", "👤 学生名单管理", "📄 导出21天记录表", "📊 历史记录总表"])

# -------------------------- 1. 复习提醒查询 (自适应+一键复制) --------------------------
if menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    q_date = st.date_input("选择日期", datetime.date.today())
    
    r_df = load_records()
    r_df['学习日期'] = pd.to_datetime(r_df['学习日期']).dt.date
    
    student_reminders = {}
    for _, row in r_df.iterrows():
        diff = (q_date - row['学习日期']).days + 1
        if diff in REVIEW_DAYS:
            name = row['姓名']
            if name not in student_reminders:
                student_reminders[name] = []
            student_reminders[name].append(row['学习日期'].strftime("%Y-%m-%d"))
            
    if student_reminders:
        st.success(f"📅 共找到 {len(student_reminders)} 位同学")
        for name, l_dates in student_reminders.items():
            # 手机端卡片布局
            with st.container():
                st.markdown(f"👤 **学生：{name}**")
                final_msg = generate_wechat_msg(name, q_date, l_dates)
                
                # 使用 st.code 实现一键复制。右上角会自动出现复制图标
                st.code(final_msg, language=None)
                st.info("👆 点击框框右上角小图标即可复制文案")
                st.divider()
    else:
        st.info("💡 该日期暂无复习任务")

# -------------------------- 2. 录入课时记录 --------------------------
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = load_students()
    active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
    
    if not active_students:
        st.warning("请先去管理后台添加学员")
    else:
        with st.form("input_form"):
            name = st.selectbox("👤 学生姓名", active_students)
            date = st.date_input("📅 学习日期", datetime.date.today())
            content = st.selectbox("📚 学习内容", LEARN_CONTENTS)
            hour = st.select_slider("⏰ 课时", options=HOURS_OPTIONS, value=1.0)
            if st.form_submit_button("💾 保存记录"):
                r_df = load_records()
                new_rec = pd.DataFrame([[name, date.strftime("%Y-%m-%d"), content, hour]], columns=r_df.columns)
                pd.concat([r_df, new_rec], ignore_index=True).to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
                st.success(f"已保存 {name} 的记录")
                st.rerun()

# -------------------------- 3. 学生名单管理 --------------------------
elif menu == "👤 学生名单管理":
    st.subheader("👥 学生库管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_form"):
            new_name = st.text_input("姓名")
            new_status = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("添加"):
                s_df = load_students()
                new_row = pd.DataFrame([[new_name, new_status, ""]], columns=s_df.columns)
                save_students(pd.concat([s_df, new_row], ignore_index=True))
                st.success("添加成功")
                st.rerun()

    s_df = load_students()
    if not s_df.empty:
        st.markdown("👇 可直接修改表格并保存")
        edited_df = st.data_editor(s_df, use_container_width=True)
        if st.button("💾 保存修改"):
            save_students(edited_df)
            st.success("名单已更新")

# -------------------------- 4. 导出21天表 --------------------------
elif menu == "📄 导出21天记录表":
    st.subheader("📄 抗遗忘表导出")
    r_df = load_records()
    names = r_df['姓名'].unique()
    if len(names) > 0:
        target = st.selectbox("选择学生", names)
        if st.button("生成"):
            student_df = r_df[r_df['姓名'] == target].sort_values("学习日期")
            output = [["单词记忆21天抗遗忘周期记录表", "", "", "", "", "", "", "", "", "", "", "", ""],
                      [f"学生姓名：{target}", "", "", "", "", "", "", "", "", "", "", "", ""],
                      ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]]
            for _, row in student_df.iterrows():
                ld = datetime.datetime.strptime(row['学习日期'], "%Y-%m-%d")
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([row['学习日期'], "", ""] + rvs)
                output.append([""]*13)
            csv_buf = io.StringIO()
            import csv
            writer = csv.writer(csv_buf)
            writer.writerows(output)
            st.download_button(f"📥 下载表格", csv_buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# -------------------------- 5. 历史记录总表 --------------------------
elif menu == "📊 历史记录总表":
    st.subheader("📊 历史明细")
    st.dataframe(load_records(), use_container_width=True)