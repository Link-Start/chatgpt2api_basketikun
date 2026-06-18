#!/usr/bin/env python3
"""
JSON 存储数据导入导出脚本

用法：
  python scripts/migrate_storage.py --export accounts.json
  python scripts/migrate_storage.py --import accounts.json
"""

import argparse
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"


def export_to_json(output_file: str):
    """导出本地 JSON 存储的数据到文件"""
    print(f"[migrate] Exporting data to {output_file}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ACCOUNTS_FILE.exists():
        accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        accounts = accounts if isinstance(accounts, list) else []
    else:
        accounts = []
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    
    print(f"[migrate] Exported {len(accounts)} accounts to {output_file}")


def import_from_json(input_file: str):
    """从 JSON 文件导入数据到本地 JSON 存储"""
    print(f"[migrate] Importing data from {input_file}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"[migrate] Error: File not found: {input_file}")
        sys.exit(1)
    
    try:
        accounts = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(accounts, list):
            print(f"[migrate] Error: Invalid JSON format, expected array")
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[migrate] Error: Invalid JSON: {e}")
        sys.exit(1)
    
    ACCOUNTS_FILE.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    
    print(f"[migrate] Imported {len(accounts)} accounts")


def main():
    parser = argparse.ArgumentParser(
        description="ChatGPT2API JSON 存储数据导入导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出当前数据到 JSON 文件
  python scripts/migrate_storage.py --export backup.json
  
  # 从 JSON 文件导入数据
  python scripts/migrate_storage.py --import backup.json
        """
    )
    parser.add_argument(
        "--export",
        dest="export_file",
        metavar="FILE",
        help="导出数据到 JSON 文件",
    )
    parser.add_argument(
        "--import",
        dest="import_file",
        metavar="FILE",
        help="从 JSON 文件导入数据",
    )
    
    args = parser.parse_args()
    
    # 检查参数
    if args.export_file:
        export_to_json(args.export_file)
    elif args.import_file:
        import_from_json(args.import_file)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
