import sys
import asyncio
import subprocess
from pathlib import Path
import argparse

def open_file_with_default_app_simp(file_path: Path) -> None:
    if sys.platform == "win32":
        # Windows: 使用 os.startfile 最简单，但这里统一用 subprocess
        # 注意：os.startfile 无法等待，但此处不需要等待
        import os
        os.startfile(str(file_path))
    elif sys.platform == "darwin":
        # macOS
        subprocess.run(["open", str(file_path)], check=True)
    else:
        # Linux / Unix
        subprocess.run(["xdg-open", str(file_path)], check=True)
async def open_file_with_default_app(file_path: Path) -> None:
    """异步用系统默认应用程序打开文件（跨平台）"""
    if sys.platform == "win32":
        # Windows: os.startfile 是同步的，但很快，放入线程池即可
        import os
        await asyncio.to_thread(os.startfile, str(file_path))
    elif sys.platform == "darwin":
        proc = await asyncio.create_subprocess_exec("open", str(file_path))
        await proc.wait()
    else:
        # Linux / Unix
        proc = await asyncio.create_subprocess_exec("xdg-open", str(file_path))
        await proc.wait()
def read_pic_simp(VOL,pagenum):
    IMAGE_DIR = Path(f"cache_images{VOL}")
    if VOL in range(261,264):
        IMAGE_DIR = Path(f"cache_images26_{VOL-260}")


    if not IMAGE_DIR.exists():
        return f"错误：图片目录不存在 -> {IMAGE_DIR}"
        sys.exit(1)
    if not IMAGE_DIR.is_dir():
        return f"错误：{IMAGE_DIR} 不是一个目录"
        sys.exit(1)

    # 2. 获取用户输入的文件名
    file_name =f"page_{pagenum:04d}.png"
    if not file_name:
        print("文件名不能为空")
        sys.exit(1)

    # 3. 构造完整路径
    target = IMAGE_DIR / file_name

    # 4. 检查文件是否存在且是普通文件
    if not target.exists():
        return f"错误：文件不存在 -> {target}"
        sys.exit(1)
    if not target.is_file():
        return f"错误：{target} 不是常规文件"
        sys.exit(1)

    # 5. 打开文件
    try:
        open_file_with_default_app_simp(target)
        return f"已打开文件：{target}"
    except Exception as e:
        return f"打开文件时出错：{e}"
        sys.exit(1)
async def read_pic(vol: int, pagenum: int, semaphore: asyncio.Semaphore) -> str:
    """
    异步根据卷号和页码打开对应图片。
    使用信号量控制并发数量。
    """
    async with semaphore:
        # 确定图片目录
        if 261 <= vol <= 263:
            image_dir = Path(f"cache_images26_{vol - 260}")
        else:
            image_dir = Path(f"cache_images{vol}")

        if not image_dir.exists():
            return f"错误：图片目录不存在 -> {image_dir}"
        if not image_dir.is_dir():
            return f"错误：{image_dir} 不是一个目录"

        file_name = f"page_{pagenum:04d}.png"
        target = image_dir / file_name

        if not target.exists():
            return f"错误：文件不存在 -> {target}"
        if not target.is_file():
            return f"错误：{target} 不是常规文件"

        try:
            await open_file_with_default_app(target)
            return f"已打开文件：{target}"
        except Exception as e:
            return f"打开文件时出错：{e}"

def parse_pages(pages_raw: list[str]) -> list[int]:
    """
    解析页码列表，支持空格和逗号混合分隔。
    例如：['1,2', '3'] -> [1,2,3]
    """
    pages = []
    for item in pages_raw:
        item=item.replace('-',',')
        if ',' in item:
            for part in item.split(','):
                part = part.strip()
                part = part.replace('[','').replace(']','')
                if part:
                    pages.append(int(part))
        else:
            item=item.replace('[','').replace(']','')
            pages.append(int(item))
    # 去重保持顺序
    return list(dict.fromkeys(pages))

async def main():
    parser = argparse.ArgumentParser(description="文献查询系统 - 异步批量打开图片")
    parser.add_argument("-v", "--vol", type=int, default=8, help="卷号（默认：8）")
    parser.add_argument("-p", "--page", nargs='+',
                        help="页码，支持空格或逗号分隔，例如：-p 1 2 3 或 -p 1,2,3 或 -p '1, 2, 3'")
    parser.add_argument("-b", "--batchpage", nargs='+',
                        help="页码，支持空格或逗号分隔，例如：-b 1 2 3 或 -b 1,2,3 或 -b '1, 2, 3'")
    parser.add_argument("-c", "--concurrent", type=int, default=16,
                        help="最大并发打开图片数量（默认：16），设为1即顺序打开")
    parser.add_argument("-s", "--start", type=int,default=5,
                        help="开始页面")
    parser.add_argument("-e", "--end", type=int,default=5,
                        help="结束页面")
    args = parser.parse_args()

    vol = args.vol
    pages = parse_pages(args.page) if args.page else (list(range(parse_pages(args.batchpage)[0],parse_pages(args.batchpage)[-1]+1)) if args.batchpage else list(range(args.start,args.end+1)))
    semaphore = asyncio.Semaphore(args.concurrent)

    print(f"卷号：{vol}，共需打开 {len(pages)} 页: {pages}")
    print(f"并发数限制：{args.concurrent}")


    # 创建所有任务
    tasks = [read_pic(vol, page, semaphore) for page in pages]
    results = await asyncio.gather(*tasks)

    for idx, res in enumerate(results, 1):
        print(f"[{idx}/{len(pages)}] {res}")

if __name__ == "__main__":
    asyncio.run(main())