#!/usr/bin/env python3
"""
Generate synthetic test PDF files for benchmark queries.
Uses markdown to HTML to PDF conversion with WeasyPrint.
"""

import argparse
import os
import importlib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
DEFAULT_WORKSPACE = os.path.join(WORKSPACE_ROOT, 'tmp_output', 'claw-input-file-generator')
SETUP_COMMAND = 'pip3 install Pillow markdown weasyprint openpyxl python-docx gTTS'

# CSS styling for PDF
PDF_CSS = '''
body {
    font-family: 'Noto Sans SC', 'WenQuanYi Zen Hei', 'Microsoft YaHei', sans-serif;
    line-height: 1.8;
    padding: 40px;
    max-width: 800px;
    margin: 0 auto;
    color: #333;
    font-size: 14px;
}

h1 {
    color: #1a365d;
    border-bottom: 3px solid #3182ce;
    padding-bottom: 10px;
    text-align: center;
    font-size: 28px;
}

h2 {
    color: #2c5282;
    border-bottom: 1px solid #bee3f8;
    padding-bottom: 8px;
    margin-top: 30px;
    font-size: 20px;
}

h3 {
    color: #2b6cb0;
    margin-top: 20px;
    font-size: 16px;
}

code {
    background-color: #f7fafc;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Fira Code', 'Courier New', monospace;
    font-size: 13px;
    color: #e53e3e;
}

pre {
    background-color: #2d3748;
    color: #e2e8f0;
    padding: 15px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 12px;
}

pre code {
    background: none;
    color: inherit;
    padding: 0;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 20px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

th {
    background-color: #3182ce;
    color: white;
    padding: 12px 15px;
    text-align: left;
}

td {
    padding: 10px 15px;
    border-bottom: 1px solid #e2e8f0;
}

tr:nth-child(even) {
    background-color: #f7fafc;
}

blockquote {
    border-left: 4px solid #ed8936;
    margin: 15px 0;
    padding: 10px 20px;
    background-color: #fffaf0;
    color: #c05621;
}

hr {
    border: none;
    height: 2px;
    background: linear-gradient(to right, transparent, #3182ce, transparent);
    margin: 30px 0;
}

strong {
    color: #1a365d;
}

ul, ol {
    margin: 10px 0;
    padding-left: 25px;
}

li {
    margin: 5px 0;
}
'''

# Sample markdown templates
TEMPLATES = {
    'backprop': '''# 反向传播算法学习笔记

**Backpropagation Algorithm Notes**

---

## 1. 基本概念

反向传播（Backpropagation）是神经网络训练中用于计算梯度的核心算法。它的主要思想是利用**链式法则**，从输出层向输入层逐层计算损失函数对每个权重的偏导数。

### 关键要点

- **前向传播**：计算各层激活值和最终输出
- **反向传播**：计算误差对各层权重的梯度
- **参数更新**：使用梯度下降更新权重

---

## 2. 符号定义

假设有一个 L 层的神经网络：

| 符号 | 含义 |
|------|------|
| x | 输入向量 |
| y | 真实标签 |
| a[l] | 第 l 层的激活值 |
| z[l] | 第 l 层的加权输入 |
| W[l] | 第 l 层的权重矩阵 |
| b[l] | 第 l 层的偏置向量 |
| σ | 激活函数 |
| L | 损失函数 |

---

## 3. 前向传播过程

对于每一层 l = 1, 2, ..., L：

```
z[l] = W[l] · a[l-1] + b[l]
a[l] = σ(z[l])
```

---

## 4. 反向传播推导

### Step 1: 计算输出层误差

```
δ[L] = ∇a L ⊙ σ'(z[L])
```

其中 ⊙ 表示逐元素乘法。

### Step 2: 反向传播误差

```
δ[l] = ((W[l+1])^T · δ[l+1]) ⊙ σ'(z[l])
```

### Step 3: 计算梯度

```
∂L/∂W[l] = δ[l] · (a[l-1])^T
∂L/∂b[l] = δ[l]
```

---

*笔记整理时间：2024年6月*
''',
    
    'report': '''# 项目报告

**Project Report**

---

## 1. 项目概述

本文档是一份项目报告模板，用于展示PDF生成功能。

---

## 2. 主要内容

### 2.1 背景介绍

项目背景说明...

### 2.2 目标

- 目标一
- 目标二
- 目标三

---

## 3. 总结

项目总结内容...

---

*报告日期：2024年*
'''
}


def generate_pdf_from_markdown(md_content, output_path, title=None):
    """Generate PDF from markdown content using WeasyPrint."""
    require_python_package('markdown', 'markdown')
    require_python_package('weasyprint', 'weasyprint')
    import markdown
    from weasyprint import HTML, CSS
    ensure_parent_dir(output_path)
    
    # Convert markdown to HTML
    html_content = markdown.markdown(
        md_content,
        extensions=['tables', 'fenced_code', 'codehilite', 'toc']
    )
    
    # Full HTML document
    full_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title or 'Document'}</title>
</head>
<body>
{html_content}
</body>
</html>'''
    
    # Generate PDF
    HTML(string=full_html).write_pdf(
        output_path,
        stylesheets=[CSS(string=PDF_CSS)]
    )
    
    return output_path


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def require_python_package(module_name, package_name):
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(
            f"Missing Python dependency '{package_name}'. "
            f"Install skill prerequisites first: {SETUP_COMMAND}"
        ) from exc


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic test PDF files')
    parser.add_argument('--template', choices=['backprop', 'report', 'custom'], 
                       default='backprop', help='Template to use')
    parser.add_argument('--output', default=None, help='Output PDF file path')
    parser.add_argument('--workspace', default=DEFAULT_WORKSPACE, help='Workspace directory')
    parser.add_argument('--content', default=None, help='Custom markdown content')
    
    args = parser.parse_args()
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        os.makedirs(args.workspace, exist_ok=True)
        default_name = {
            'backprop': 'backprop_notes.pdf',
            'report': 'project_report.pdf',
            'custom': 'custom_document.pdf',
        }[args.template]
        output_path = os.path.join(args.workspace, 'notes', default_name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Get content
    if args.content:
        md_content = args.content
    elif args.template == 'custom':
        raise SystemExit("Error: --content required for custom template")
    else:
        md_content = TEMPLATES[args.template]
    
    # Generate PDF
    generate_pdf_from_markdown(md_content, output_path, title=args.template)
    if not os.path.exists(output_path):
        raise SystemExit(f"Generator did not create the expected file: {output_path}")
    print(f"Generated: {output_path}")


if __name__ == '__main__':
    main()
