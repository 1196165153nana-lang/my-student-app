# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random
from collections import defaultdict
import numpy as np

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 新增豆包密钥读取
DOUBAO_API_KEY = st.secrets.get("DOUBAO_API_KEY", "")

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词"]

# ===================== 【这里粘贴你原来全部飞书工具函数】=====================
# get_feishu_token()
# fetch_students_table()
# fetch_records_table()
# update_feishu_record()
# create_feishu_record()
# .......你原有所有接口函数全部放此处
# =========================================================================

# 工具函数：安全求和，规避numpy float64、NaN崩溃
def safe_sum(series):
    s = series.sum()
    if pd.isna(s):
        return 0.0
    return float(s)

# 工具函数：安全格式化数字
def safe_fmt_float(val, dec=1):
    if pd.isna(val):
        return 0.0
    return float(val)

# -------------------------- 页面布局与侧边菜单 --------------------------
st.set_page_config(page_title="单词教学管理系统", layout="wide")
menu = st.sidebar.selectbox(
    "功能菜单",
    ["🏠主页", "👨‍🎓学生管理", "📝上课记录", "📊月结算导出", "📖单词训练流程", "💬评语助手"]
)

# ====================== 主页 ======================
if menu == "🏠主页":
    st.title("单词教学管理系统")
    st.info("飞书多维表格后端｜多老师权限基于飞书教师权限表")
    st.markdown("""
- 学生表：belong_openid 归属教师
- 上课记录表：teacher_openid 授课教师
""")

# ====================== 学生管理 ======================
elif menu == "👨‍🎓学生管理":
    st.header("学生管理")
    # 此处粘贴你原有学生管理全部代码

# ====================== 上课记录 ======================
elif menu == "📝上课记录":
    st.header("上课记录录入/编辑")
    # 此处粘贴你原有上课记录全部代码

# ====================== 【修复重点】月结算导出模块 ======================
elif menu == "📊月结算导出":
    st.header("📊 月度结算表导出")
    col1, col2 = st.columns(2)
    with col1:
        sel_year = st.selectbox("年份", list(range(2024,2031)), index=2)
    with col2:
        sel_month = st.selectbox("月份", list(range(1,13)), index=datetime.date.today().month-1)

    # 拉取数据
    df_stu = fetch_students_table()   # 你的原有函数
    df_rec = fetch_records_table()    # 你的原有函数

    # 构建：学生姓名→状态映射，用于导出时追加(结课)
    stu_status_map = {}
    for _,row in df_stu.iterrows():
        name = row.get("学生姓名","")
        status = row.get("状态","")
        stu_status_map[name] = status

    # 筛选当月记录逻辑（保留你原有逻辑）
    df_rec["dt"] = pd.to_datetime(df_rec["上课日期"], errors="coerce")
    mask = (df_rec["dt"].dt.year==sel_year) & (df_rec["dt"].dt.month==sel_month)
    df_month = df_rec[mask].copy()

    if df_month.empty:
        st.warning("⚠️本月暂无上课记录")
    else:
        # 聚合统计
        stat_df = df_month.groupby("学生姓名").agg({
            "数量":"sum",
            "应发工资":"sum"
        }).reset_index()

        # --------关键修复：全部转为python原生float，干掉numpy.float64/NaN崩溃--------
        total_h = safe_sum(stat_df["数量"])
        total_money = safe_sum(stat_df["应发工资"])

        st.info(f"✅ 课时总数：{total_h:.1f} h｜应发总金额：¥{total_money:.0f}")

        # 给导出表格学生姓名追加 (结课)
        def append_finish_tag(name):
            s = stu_status_map.get(name,"")
            if s == "结课":
                return f"{name}(结课)"
            return name

        stat_df["导出姓名"] = stat_df["学生姓名"].apply(append_finish_tag)
        out_df = stat_df[["导出姓名","数量","应发工资"]].copy()

        # csv导出
        buf = io.StringIO()
        out_df.to_csv(buf, index=False, encoding="utf‑8‑sig")
        csv_bytes = buf.getvalue().encode("utf‑8‑sig")
        st.download_button(
            label="📥下载本月结算CSV",
            data=csv_bytes,
            file_name=f"{sel_year}_{sel_month}_月结算.csv",
            mime="text/csv"
        )
        st.dataframe(out_df, use_container_width=True)

# ====================== 单词训练流程页面 ======================
elif menu == "📖单词训练流程":
    st.header("📖单词带背训练流程")
    st.markdown("""
### 完整训练步骤
1. 新词学习：新词输入，标记初次记忆
2. 当堂第一轮复习
3. 当堂第二轮检测
4. 根据REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]排定后续复习日期
5. 每次上课优先完成到期复习，再学习新词
""")
    st.subheader("复习评语模板")
    c1,c2 = st.columns(2)
    with c1:
        st.code("复习整体掌握扎实，原有能力保持稳定，继续坚持巩固。", language=None)
    with c2:
        st.code("本节课复习反馈良好，已学内容无明显遗忘，维持现有节奏稳步积累。", language=None)
        st.code("部分单词熟练度不足，标记待复习，后续课堂重点复盘巩固。", language=None)

# ====================== 评语助手（预留豆包AI调用） ======================
elif menu == "💬评语助手":
    st.header("AI课堂评语美化")
    raw_text = st.text_area("粘贴原始课堂反馈","")
    if st.button("✨AI生成润色评语"):
        if not DOUBAO_API_KEY:
            st.error("未配置DOUBAO_API_KEY，请在secrets添加")
        else:
            # 这里粘贴你豆包请求函数
            st.info("调用逻辑待填入")

