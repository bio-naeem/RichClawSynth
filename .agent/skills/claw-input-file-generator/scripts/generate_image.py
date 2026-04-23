#!/usr/bin/env python3
"""
Generate synthetic test images for benchmark queries.
Supports: sales reports, supplier quotes, financial reports, complaint forms,
blackboards, prescriptions, etc.
"""

import argparse
import os
import random
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
DEFAULT_WORKSPACE = os.path.join(WORKSPACE_ROOT, 'tmp_output', 'claw-input-file-generator')

def get_font(size):
    """Load Chinese font with fallback."""
    fonts_to_try = [
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for font_path in fonts_to_try:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                continue
    return ImageFont.load_default()


def generate_sales_report(month_name, page_num, filename):
    """Generate a sales data report image."""
    width, height = 800, 600
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(28)
    font_subtitle = get_font(16)
    font_header = get_font(13)
    font_cell = get_font(12)
    font_small = get_font(11)
    
    # Header
    title = "2024年Q1销售数据报表"
    subtitle = "XX集团有限公司 · 销售部"
    draw.text((width//2, 35), title, font=font_title, fill='#1a1a1a', anchor='mm')
    draw.text((width//2, 65), subtitle, font=font_subtitle, fill='#666666', anchor='mm')
    draw.text((width - 40, 90), f"第 {page_num} 页 / 共 3 页", font=font_small, fill='#999999', anchor='rt')
    
    # Table data
    products = ['电子产品', '家居用品', '服装鞋帽', '食品饮料', '美妆护肤']
    sales_data = [
        (850 + page_num * 50, 12.5, 12500 + page_num * 500),
        (620 + page_num * 50, -3.2, 8500 + page_num * 500),
        (480 + page_num * 50, 8.7, 15000 + page_num * 500),
        (350 + page_num * 50, 15.3, 22000 + page_num * 500),
        (280 + page_num * 50, 22.1, 9500 + page_num * 500),
    ]
    prices = [680, 729, 320, 159, 295]
    
    # Table
    table_top = 110
    row_height = 32
    col_widths = [100, 70, 100, 110, 100, 100, 100]
    col_x = [40]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)
    
    headers = ['产品线', '月份', '销售额(万元)', '去年同期(万元)', '同比增长率', '销售量(件)', '平均单价(元)']
    
    # Draw header
    for i, (header, x) in enumerate(zip(headers, col_x)):
        draw.rectangle([x, table_top, x + col_widths[i], table_top + row_height], fill='#2c5aa0', outline='#1e3d6b')
        draw.text((x + col_widths[i]//2, table_top + row_height//2), header, font=font_header, fill='white', anchor='mm')
    
    # Draw data rows
    for row_idx, (product, data) in enumerate(zip(products, sales_data)):
        y = table_top + (row_idx + 1) * row_height
        sales, growth, qty = data
        sales = sales + row_idx * 10
        last_year = int(sales / (1 + growth/100))
        price = prices[row_idx]
        
        bg_color = '#f8f9fa' if row_idx % 2 == 0 else 'white'
        
        row_data = [product, month_name, str(sales), str(last_year), 
                   f"{'+' if growth >= 0 else ''}{growth}%", str(qty), f"¥{price}"]
        
        for i, (cell, x) in enumerate(zip(row_data, col_x)):
            draw.rectangle([x, y, x + col_widths[i], y + row_height], fill=bg_color, outline='#dddddd')
            color = '#28a745' if i == 4 and growth >= 0 else '#dc3545' if i == 4 else '#333333'
            draw.text((x + col_widths[i]//2, y + row_height//2), cell, font=font_cell, fill=color, anchor='mm')
    
    # Footer
    notes_y = table_top + 6 * row_height + 20
    draw.rectangle([40, notes_y, width - 40, notes_y + 40], fill='#f5f5f5', outline='#e0e0e0')
    draw.text((50, notes_y + 12), "备注：数据统计截止日期为每月最后一日，同比增长率为与2023年同期对比。", font=font_small, fill='#666666')
    draw.text((width//2, height - 25), "制表人：销售部数据组 | 制表日期：2024年4月2日 | 内部资料，请勿外传", font=font_small, fill='#999999', anchor='mm')
    
    img.save(filename, 'JPEG', quality=95)
    return filename


def generate_supplier_quote(supplier_idx, filename):
    """Generate a supplier quotation image."""
    width, height = 800, 700
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(22)
    font_header = get_font(14)
    font_cell = get_font(12)
    font_small = get_font(11)
    font_info = get_font(12)
    
    suppliers = [
        ('华强电子科技有限公司', '张经理', '138-1234-5678'),
        ('东方元器件供应商行', '李经理', '139-2345-6789'),
        ('创新科技材料有限公司', '王经理', '137-3456-7890'),
        ('永达工业物资有限公司', '赵经理', '136-4567-8901'),
        ('盛世电子元器件有限公司', '刘经理', '135-5678-9012'),
    ]
    
    materials = [
        ('电阻R0805', '10KΩ ±5%', 0.02, '只'),
        ('电容C0805', '100μF/16V', 0.08, '只'),
        ('二极管1N4148', 'DO-35', 0.05, '只'),
        ('LED灯珠', '5mm 白色', 0.15, '只'),
        ('IC芯片STM32F103', 'LQFP48', 12.50, '片'),
        ('接插件JST-XH', '2P 2.5mm', 0.35, '个'),
        ('电感100μH', 'CD54', 0.45, '只'),
        ('晶振8MHz', 'HC49S', 0.25, '只'),
    ]
    
    supplier_name, contact, phone = suppliers[supplier_idx]
    quote_no = f"BJ-20240613-{supplier_idx+1:03d}"
    
    # Title
    draw.text((width//2, 30), "供应商报价单", font=font_title, fill='#1a1a1a', anchor='mm')
    
    # Supplier info
    draw.rectangle([30, 50, 380, 110], outline='#cccccc', fill='#fafafa')
    draw.text((40, 58), f"供应商：{supplier_name}", font=font_info, fill='#333333')
    draw.text((40, 78), f"联系人：{contact}", font=font_info, fill='#333333')
    draw.text((40, 98), f"电  话：{phone}", font=font_info, fill='#333333')
    
    # Quote info
    draw.rectangle([420, 50, 770, 110], outline='#cccccc', fill='#fafafa')
    draw.text((430, 58), f"报价单号：{quote_no}", font=font_info, fill='#333333')
    draw.text((430, 78), f"报价日期：2024年06月13日", font=font_info, fill='#333333')
    draw.text((430, 98), f"有效期限：30天", font=font_info, fill='#333333')
    
    # Table
    table_top = 130
    row_height = 28
    col_widths = [50, 150, 130, 80, 80, 80, 70, 80]
    col_x = [30]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)
    
    headers = ['序号', '物料名称', '规格型号', '单价(元)', '数量', '单位', '金额(元)', '备注']
    
    # Draw header
    for i, (header, x) in enumerate(zip(headers, col_x)):
        draw.rectangle([x, table_top, x + col_widths[i], table_top + row_height], fill='#2c5aa0', outline='#1e3d6b')
        draw.text((x + col_widths[i]//2, table_top + row_height//2), header, font=font_header, fill='white', anchor='mm')
    
    # Select materials
    random.seed(supplier_idx * 100)
    selected = random.sample(materials, min(6, len(materials)))
    
    total_amount = 0
    for row_idx, (mat_name, spec, base_price, unit) in enumerate(selected):
        y = table_top + (row_idx + 1) * row_height
        price_var = 1 + (supplier_idx - 2) * 0.08 + random.uniform(-0.1, 0.1)
        price = round(base_price * price_var, 2)
        qty = random.choice([100, 500, 1000, 2000, 5000])
        amount = round(price * qty, 2)
        total_amount += amount
        
        row_data = [str(row_idx + 1), mat_name, spec, f"{price:.2f}", str(qty), unit, f"{amount:.2f}", '']
        
        bg_color = '#f8f9fa' if row_idx % 2 == 0 else 'white'
        
        for i, (cell, x) in enumerate(zip(row_data, col_x)):
            draw.rectangle([x, y, x + col_widths[i], y + row_height], fill=bg_color, outline='#dddddd')
            draw.text((x + col_widths[i]//2, y + row_height//2), cell, font=font_cell, fill='#333333', anchor='mm')
    
    # Total row
    y = table_top + (len(selected) + 1) * row_height
    draw.rectangle([col_x[0], y, col_x[5] + col_widths[5], y + row_height], fill='#e8f4fc', outline='#2c5aa0')
    draw.text((col_x[0] + (col_x[5] + col_widths[5] - col_x[0])//2, y + row_height//2), '合计金额（不含税）', font=font_cell, fill='#1e3d6b', anchor='mm')
    draw.rectangle([col_x[6], y, col_x[6] + col_widths[6], y + row_height], fill='#e8f4fc', outline='#2c5aa0')
    draw.text((col_x[6] + col_widths[6]//2, y + row_height//2), f"{total_amount:.2f}", font=font_cell, fill='#c00', anchor='mm')
    
    # Footer
    draw.text((width//2, height - 25), "本报价单一式两份，供需双方各执一份，具有同等法律效力", font=font_small, fill='#999999', anchor='mm')
    
    img.save(filename, 'JPEG', quality=95)
    return filename


def generate_financial_report(company_idx, filename):
    """Generate a financial report image."""
    width, height = 900, 800
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(24)
    font_subtitle = get_font(14)
    font_header = get_font(13)
    font_cell = get_font(12)
    font_small = get_font(11)
    font_bold = get_font(13)
    
    companies = [
        {'name': '天启智能科技股份有限公司', 'stock': '688XXX', 
         'data': {'营业收入': '128,560', '净利润': '18,720', '毛利率': '35.9%', '资产负债率': '47.9%', 'ROE': '19.3%'}},
        {'name': '星辰电子科技有限公司', 'stock': '300XXX',
         'data': {'营业收入': '89,230', '净利润': '8,960', '毛利率': '31.1%', '资产负债率': '46.9%', 'ROE': '13.5%'}},
        {'name': '银河创新技术股份有限公司', 'stock': '002XXX',
         'data': {'营业收入': '156,780', '净利润': '9,230', '毛利率': '30.5%', '资产负债率': '57.9%', 'ROE': '8.9%'}},
    ]
    
    company = companies[company_idx]
    
    # Header
    draw.rectangle([0, 0, width, 60], fill='#1e3d6b')
    draw.text((width//2, 30), f"{company['name']}财务报表", font=font_title, fill='white', anchor='mm')
    
    draw.text((30, 75), f"股票代码：{company['stock']}", font=font_subtitle, fill='#333333')
    draw.text((200, 75), f"报告期间：2023年度", font=font_subtitle, fill='#333333')
    
    # Key metrics
    draw.rectangle([20, 100, width - 20, 250], outline='#28a745', width=2)
    draw.rectangle([20, 100, width - 20, 125], fill='#28a745')
    draw.text((width//2, 112), "关键财务指标", font=font_header, fill='white', anchor='mm')
    
    metrics = [
        ('营业收入', company['data']['营业收入'], '万元'),
        ('净利润', company['data']['净利润'], '万元'),
        ('毛利率', company['data']['毛利率'], ''),
        ('资产负债率', company['data']['资产负债率'], ''),
        ('ROE', company['data']['ROE'], ''),
    ]
    
    y = 140
    for i, (name, value, unit) in enumerate(metrics):
        col = i % 3
        row = i // 3
        x = 40 + col * 280
        y_pos = 140 + row * 50
        
        draw.rectangle([x, y_pos, x + 260, y_pos + 45], fill='#f0fff0', outline='#90ee90')
        draw.text((x + 130, y_pos + 15), name, font=font_cell, fill='#333', anchor='mm')
        draw.text((x + 130, y_pos + 32), f"{value}{' ' + unit if unit else ''}", font=font_bold, fill='#28a745', anchor='mm')
    
    # Footer
    draw.text((width//2, height - 30), f"数据来源：公开披露年报 | 整理日期：2024年6月14日", font=font_small, fill='#999999', anchor='mm')
    
    img.save(filename, 'PNG')
    return filename


def generate_blackboard(board_idx, filename):
    """Generate a blackboard-style image with math formulas."""
    width, height = 800, 600
    img = Image.new('RGB', (width, height), '#1a4d1a')
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(20)
    font_content = get_font(16)
    font_formula = get_font(14)
    
    chalk_white = '#ffffff'
    chalk_yellow = '#ffff99'
    chalk_pink = '#ffccff'
    
    draw.rectangle([5, 5, width-5, height-5], outline='#8b4513', width=8)
    
    content = [
        ("第三章 多元函数微分学", [
            "§3.1 偏导数",
            "定义：设 z = f(x,y) 在点(x₀,y₀)的某邻域内有定义",
            "∂z/∂x = lim[Δx→0] [f(x₀+Δx,y₀)-f(x₀,y₀)]/Δx",
            "例1：求 z = x²y + sin(xy) 的偏导数",
            "解：∂z/∂x = 2xy + y·cos(xy)",
        ]),
        ("§3.3 梯度与方向导数", [
            "grad f = ∇f = (∂f/∂x, ∂f/∂y, ∂f/∂z)",
            "方向导数：∂f/∂l = ∇f · l⃗ = |∇f|·cosθ",
            "例2：f(x,y) = x²+y²，求在点(1,2)沿方向(3,4)的方向导数",
        ]),
        ("§3.4 多元函数极值", [
            "极值必要条件：∂f/∂x|₀ = 0, ∂f/∂y|₀ = 0",
            "判别法：Δ = AC - B²",
            "Δ>0, A>0 ⇒ 极小值; Δ>0, A<0 ⇒ 极大值",
            "拉格朗日乘数法：L(x,y,λ) = f(x,y) + λ·g(x,y)",
        ]),
    ]
    
    current = content[board_idx % len(content)]
    y = 30
    
    draw.text((40, y), current[0], font=font_title, fill=chalk_white)
    y += 35
    draw.line([(40, y), (width-40, y)], fill=chalk_white, width=1)
    y += 20
    
    for line in current[1]:
        draw.text((40, y), line, font=font_formula, fill=chalk_white)
        y += 25
    
    img.save(filename, 'JPEG', quality=90)
    return filename


def generate_prescription(presc_idx, filename):
    """Generate a Chinese medicine prescription image."""
    width, height = 700, 800
    img = Image.new('RGB', (width, height), '#f5f0e6')
    draw = ImageDraw.Draw(img)
    
    font_title = get_font(24)
    font_header = get_font(14)
    font_content = get_font(15)
    font_small = get_font(12)
    
    prescriptions = [
        {'title': '調經養血湯', 'herbs': ['當歸 12g', '川芎 9g', '白芍 15g', '熟地黃 20g', '香附 10g']},
        {'title': '清熱解毒方', 'herbs': ['金銀花 15g', '連翹 12g', '板藍根 20g', '黃芩 10g', '梔子 9g']},
        {'title': '健脾益氣散', 'herbs': ['黨參 15g', '白朮 12g', '茯苓 15g', '山藥 20g', '陳皮 9g']},
        {'title': '祛風除濕湯', 'herbs': ['獨活 10g', '羌活 10g', '防風 9g', '秦艽 12g', '威靈仙 10g']},
        {'title': '養心安神方', 'herbs': ['酸棗仁 15g', '柏子仁 12g', '遠志 9g', '茯神 15g', '龍骨 30g']},
    ]
    
    presc = prescriptions[presc_idx % len(prescriptions)]
    
    draw.text((width//2, 40), presc['title'], font=font_title, fill='#2c1810', anchor='mm')
    draw.line([(100, 65), (width-100, 65)], fill='#8b4513', width=1)
    
    y = 120
    draw.text((50, y), f"處方編號：ZY-{presc_idx+1:03d}", font=font_header, fill='#4a3728')
    y += 30
    draw.text((50, y), "藥材組成：", font=font_header, fill='#2c1810')
    y += 30
    
    for herb in presc['herbs']:
        draw.text((60, y), f"  {herb}", font=font_content, fill='#1a1a1a')
        y += 28
    
    y += 20
    draw.text((50, y), "煎服方法：每日一劑，水煎分兩次溫服", font=font_header, fill='#2c1810')
    y += 40
    draw.text((50, y), "醫師簽章：", font=font_header, fill='#4a3728')
    
    draw.text((width//2, height - 30), "XX中醫館 處方箋", font=font_small, fill='#999999', anchor='mm')
    
    img.save(filename, 'JPEG', quality=85)
    return filename


def generate_complaint_form(filename):
    """Generate a handwritten-style customer complaint form image."""
    width, height = 760, 980
    img = Image.new('RGB', (width, height), '#f7f2e8')
    draw = ImageDraw.Draw(img)

    font_title = get_font(24)
    font_header = get_font(16)
    font_content = get_font(15)
    font_small = get_font(12)

    ink = '#2b2b2b'
    line = '#9c8f7a'

    draw.rectangle([18, 18, width - 18, height - 18], outline='#7d6f5a', width=2)
    draw.text((width // 2, 50), "客户投诉登记表", font=font_title, fill=ink, anchor='mm')
    draw.text((width - 40, 86), "编号：TS-202406-018", font=font_small, fill='#6d6456', anchor='rt')

    sections = [
        ("客户姓名", "李女士"),
        ("联系电话", "139****6721"),
        ("订单编号", "ORD-20240618-2357"),
        ("购买渠道", "线上旗舰店"),
        ("产品名称", "智能空气炸锅 Pro"),
        ("投诉时间", "2024-06-21 19:45"),
    ]

    y = 110
    for left, right in sections:
        draw.text((50, y), f"{left}：", font=font_header, fill=ink)
        draw.line([(150, y + 20), (690, y + 20)], fill=line, width=1)
        draw.text((160, y + 2), right, font=font_content, fill=ink)
        y += 52

    draw.text((50, y + 10), "投诉内容：", font=font_header, fill=ink)
    box_top = y + 40
    box_bottom = box_top + 230
    draw.rectangle([50, box_top, 690, box_bottom], outline=line, width=1)

    complaint_lines = [
        "收到商品后首次使用即出现异响，",
        "加热 10 分钟后机器自动断电，",
        "重新插电后面板无法正常启动。",
        "客服建议我拍视频，但我认为这是产品质量问题，",
        "希望尽快安排换货并补偿来回运费。",
    ]
    text_y = box_top + 18
    for complaint_line in complaint_lines:
        draw.text((68, text_y), complaint_line, font=font_content, fill=ink)
        text_y += 34

    draw.text((50, box_bottom + 28), "客户诉求：", font=font_header, fill=ink)
    draw.rectangle([50, box_bottom + 58, 690, box_bottom + 158], outline=line, width=1)
    draw.text((68, box_bottom + 78), "1. 3 个工作日内完成换货", font=font_content, fill=ink)
    draw.text((68, box_bottom + 112), "2. 报销寄回快递费用", font=font_content, fill=ink)

    footer_y = box_bottom + 200
    draw.text((50, footer_y), "登记人：王敏", font=font_header, fill=ink)
    draw.text((300, footer_y), "处理状态：待核实", font=font_header, fill=ink)
    draw.text((50, footer_y + 46), "签名：", font=font_header, fill=ink)
    draw.line([(105, footer_y + 65), (250, footer_y + 65)], fill=line, width=1)
    draw.text((width // 2, height - 34), "客户服务中心内部记录，请勿外传", font=font_small, fill='#8d8478', anchor='mm')

    img.save(filename, 'JPEG', quality=90)
    return filename


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic test images')
    parser.add_argument('--type', choices=['sales', 'quote', 'finance', 'blackboard', 'prescription', 'complaint', 'all'], 
                       default='all', help='Type of image to generate')
    parser.add_argument('--output', default=DEFAULT_WORKSPACE, help='Output directory')
    parser.add_argument('--count', type=int, default=3, help='Number of images to generate')
    
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    
    generated = []
    
    if args.type in ['sales', 'all']:
        months = [('一月', 1), ('二月', 2), ('三月', 3)]
        for month_name, page_num in months[:args.count]:
            filename = os.path.join(args.output, f'sales_q1_page{page_num}.jpg')
            generate_sales_report(month_name, page_num, filename)
            generated.append(filename)
    
    if args.type in ['quote', 'all']:
        for i in range(min(args.count, 5)):
            filename = os.path.join(args.output, f'supplier_quote_{i+1}.jpg')
            generate_supplier_quote(i, filename)
            generated.append(filename)
    
    if args.type in ['finance', 'all']:
        for i in range(min(args.count, 3)):
            filename = os.path.join(args.output, f'img{i+1}.png')
            generate_financial_report(i, filename)
            generated.append(filename)
    
    if args.type in ['blackboard', 'all']:
        for i in range(min(args.count, 3)):
            filename = os.path.join(args.output, f'board_{i+1}.jpg')
            generate_blackboard(i, filename)
            generated.append(filename)
    
    if args.type in ['prescription', 'all']:
        for i in range(min(args.count, 5)):
            filename = os.path.join(args.output, f'prescription_{i+1:02d}.jpg')
            generate_prescription(i, filename)
            generated.append(filename)

    if args.type in ['complaint', 'all']:
        filename = os.path.join(args.output, 'complaint_photo.jpg')
        generate_complaint_form(filename)
        generated.append(filename)
    
    print(f"Generated {len(generated)} images:")
    for f in generated:
        print(f"  {f}")


if __name__ == '__main__':
    main()
