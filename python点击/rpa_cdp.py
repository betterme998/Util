#"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="D:\edge_rpa_profile" 用调试模式启动 Edge
#手动点击左侧菜单进入【订单管理】->【发货单列表】
# D:\代码\工具\浏览器点击
# python rpa_cdp.py
import asyncio
import re
import random
import keyboard
import json
import os
from playwright.async_api import async_playwright

# ==========================================
# ⚙️ 业务配置区
# ==========================================
TARGET_URL_KEYWORD = "nmm80"
MAX_PAGES = 50
CHECK_PHONE = True
ONLY_UNMARKED = True        # ⭐ True=只点击未被油猴标记(matched-row)的订单；False=全部点击
PROGRESS_FILE = "progress.json"

is_paused = False

def toggle_pause(e):
    global is_paused
    is_paused = not is_paused
    print("\n⏸️ 已暂停，按 F9 继续..." if is_paused else "\n▶️ 继续执行...")
keyboard.on_press_key("F9", toggle_pause)

async def check_pause():
    while is_paused:
        await asyncio.sleep(1)

async def human_delay(min_sec=1.2, max_sec=4.5):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

PHONE_PATTERN = re.compile(r'(?<![a-zA-Z0-9])(1[3-9]\d{9}|1[3-9]\d\*+\d{0,4})(?![a-zA-Z0-9])')

# ==========================================
# 🌟 强化版：充满随机性的物理鼠标点击
# ==========================================
async def human_click(page, locator):
    try:
        box = await locator.bounding_box()
        if box:
            x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
            y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
            await page.mouse.move(
                x + random.randint(-150, 150),
                y + random.randint(-150, 150),
                steps=random.randint(5, 15)
            )
            await asyncio.sleep(random.uniform(0.1, 0.4))
            await page.mouse.move(x, y, steps=random.randint(10, 25))
            await asyncio.sleep(random.uniform(0.1, 0.3))
        await locator.click()
        return True
    except Exception:
        await locator.click()
        return False

async def human_scroll(page):
    try:
        scroll_y = random.choice([-300, -200, 100, 200, 350, 500])
        await page.mouse.wheel(0, scroll_y)
        await asyncio.sleep(random.uniform(0.5, 1.8))
    except Exception: pass

async def human_distraction(page):
    action = random.choice(["scroll", "hover", "do_nothing"])
    if action == "scroll":
        await human_scroll(page)
    elif action == "hover":
        try:
            await page.mouse.move(random.randint(10, 100), random.randint(10, 100), steps=random.randint(10, 20))
        except Exception: pass
    await asyncio.sleep(random.uniform(0.5, 2.0))

async def get_current_page_num(page):
    for _ in range(5):
        try:
            if page.is_closed(): return 1
            for frame in page.frames:
                active = frame.locator('.el-pager li.number.active')
                if await active.count() > 0:
                    text = await active.first.inner_text()
                    if text.strip().isdigit():
                        return int(text.strip())
        except Exception: pass
        await asyncio.sleep(1)
    return 1

async def get_task_fingerprint(page):
    try:
        if page.is_closed(): return "unknown"
        total_text = ""
        first_order = ""
        for frame in page.frames:
            total_loc = frame.locator('.el-pagination__total')
            if await total_loc.count() > 0:
                total_text = await total_loc.first.inner_text()
                break
        for frame in page.frames:
            order_locators = frame.locator('a.el-link').filter(has_text=re.compile(r"26\d{10,}"))
            if await order_locators.count() > 0:
                first_order = await order_locators.first.inner_text()
                break
        return f"{total_text}|{first_order}"
    except Exception: return "unknown"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return None

def save_progress(page, index, fingerprint):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "fingerprint": fingerprint,
            "page": page,
            "index": index,
            "only_unmarked": ONLY_UNMARKED,
        }, f, ensure_ascii=False)

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

# ==========================================
# ⭐ 核心改动：全量定位器，由主循环自行判断标记
# ==========================================
async def get_orders_locator(page, only_unmarked=False):
    if only_unmarked is None:
        only_unmarked = ONLY_UNMARKED

    base = 'tr.el-table__row:not(.matched-row) a.el-link' if only_unmarked else 'a.el-link'
    pattern = re.compile(r"26\d{10,}")

    if page.is_closed():
        return page.locator('.dummy-class')

    loc = page.locator(base).filter(has_text=pattern)
    if await loc.count() > 0:
        return loc
    for frame in page.frames:
        try:
            loc = frame.locator(base).filter(has_text=pattern)
            if await loc.count() > 0:
                return loc
        except Exception:
            pass
    return page.locator(base).filter(has_text=pattern)

async def turn_page(page, next_page_num):
    if page.is_closed(): return False
    for frame in page.frames:
        try:
            page_num_btn = frame.locator('.el-pager li.number').filter(has_text=re.compile(rf"^{next_page_num}$"))
            if await page_num_btn.count() > 0:
                await asyncio.sleep(random.uniform(1.5, 3.5))
                await human_click(page, page_num_btn.first)
                return True
        except Exception: pass
    for frame in page.frames:
        try:
            jump_input = frame.locator('.el-pagination__jump input')
            if await jump_input.count() > 0:
                await asyncio.sleep(random.uniform(1.0, 2.5))
                await jump_input.first.fill(str(next_page_num))
                await jump_input.first.press("Enter")
                return True
        except Exception: pass
    return False

# ==========================================
# 🚀 主程序
# ==========================================
async def main():
    global is_paused

    async with async_playwright() as p:
        print("\n🔌 正在连接 Edge 浏览器...")
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return

        list_page = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if TARGET_URL_KEYWORD in pg.url and not pg.is_closed():
                    list_page = pg
                    break
            if list_page: break

        if not list_page:
            print("❌ 没找到包含关键词的后台页面！")
            return

        print(f"✅ 已锁定后台标签页: {list_page.url}")
        await list_page.bring_to_front()

        mode_str = "仅点击【未命中名单】的订单 (跳过 matched-row)" if ONLY_UNMARKED else "点击【全部】订单"
        print(f"🎯 当前模式: {mode_str}")

        print("\n⚠️ 请在你的浏览器中，手动填入查询条件，并点击【查询】。")
        input("数据出来之后，请按【回车键】让脚本接管...")

        print("⏳ 正在等待页面完全渲染...")
        await asyncio.sleep(3)

        current_ui_page = await get_current_page_num(list_page)
        fingerprint = await get_task_fingerprint(list_page)

        print(f"📍 检测到你当前停留在第 {current_ui_page} 页。")

        saved_data = load_progress()

        if saved_data:
            if saved_data.get("only_unmarked") != ONLY_UNMARKED:
                print(f"\n⚠️ 点击模式已改变（上次={saved_data.get('only_unmarked')}，本次={ONLY_UNMARKED}），历史进度作废，重新开始。")
                saved_data = None
                clear_progress()

        if saved_data:
            print(f"\n📂 发现历史进度：上次处理到了第 {saved_data['page']} 页，第 {saved_data['index'] + 1} 条。")
            if fingerprint == "unknown" or saved_data.get("fingerprint") == fingerprint:
                choice = input("是否从上次中断的地方继续？(输入 y 继续，输入 n 重新开始): ").strip().lower()
                if choice == 'y':
                    start_page = saved_data['page']
                    start_index = saved_data['index']
                    fingerprint = saved_data.get('fingerprint', fingerprint)
                else:
                    start_page, start_index = current_ui_page, 0
                    clear_progress()
            else:
                print("\n🔄 检测到查询数据已变化，自动重置进度。")
                start_page, start_index = current_ui_page, 0
                clear_progress()
        else:
            print("🆕 未发现历史进度，从当前页开始。")
            start_page, start_index = current_ui_page, 0

        if start_page != current_ui_page:
            print(f"⏩ 准备从第 {current_ui_page} 页跳转到断点第 {start_page} 页...")
            success = await turn_page(list_page, start_page)

            await asyncio.sleep(4)

            new_ui_page = await get_current_page_num(list_page)
            if new_ui_page == start_page:
                print(f"✅ 成功跳转到第 {start_page} 页")
            else:
                print(f"⚠️ 自动跳转未生效（当前在第 {new_ui_page} 页）。")
                print(f"👉 请手动在浏览器点击跳到第 {start_page} 页，然后回到这里按回车继续...")
                input()

                manual_page = await get_current_page_num(list_page)
                if manual_page != start_page:
                    print(f"⚠️ 你当前在第 {manual_page} 页，与断点页不符，为防止数据遗漏，从当前页第一条开始。")
                    start_page = manual_page
                    start_index = 0
                else:
                    print(f"✅ 已确认处于第 {start_page} 页，继续从第 {start_index + 1} 条开始。")

        print(f"🚀 脚本已接管！从第 {start_page} 页，第 {start_index + 1} 条开始处理。")
        save_progress(start_page, start_index, fingerprint)

        page_num = start_page
        processed_count = 0

        while page_num <= MAX_PAGES:
            await check_pause()
            print(f"\n================ 正在处理第 {page_num} 页 ================")

            if ONLY_UNMARKED:
                print("  ⏳ 等待油猴脚本完成本页标记...")
                await asyncio.sleep(2.5)

            count = 0
            print("  ⏳ 等待表格加载", end="", flush=True)
            for _ in range(15):
                try:
                    # ⭐ 强制获取该页【全部】订单，以便下面能准确打印出跳过的日志
                    order_locators = await get_orders_locator(list_page, only_unmarked=False)
                    count = await order_locators.count()
                    if count > 0:
                        break
                except Exception: pass
                print(".", end="", flush=True)
                await asyncio.sleep(1)

            print(f" 完成！共 {count} 条。")

            if count == 0:
                print("🛑 没找到订单。")
                break

            for i in range(count):
                if page_num == start_page and i < start_index:
                    print(f"  ⏩ 跳过第 {i+1} 条 (断点前已处理)...")
                    continue

                # ⭐ 核心：在进入第一层之前，检查该行是否被油猴标记
                if ONLY_UNMARKED:
                    is_marked = False
                    try:
                        current_order = order_locators.nth(i)
                        # 判断父级 tr 类名是否包含 matched-row
                        tr_class = await current_order.locator("xpath=ancestor::tr[1]").get_attribute("class")
                        if tr_class and "matched-row" in tr_class:
                            is_marked = True
                        # 作为备用，看看是否有标签元素
                        elif await current_order.locator("xpath=ancestor::tr[1]//span[contains(@class, 'match-badge')]").count() > 0:
                            is_marked = True
                    except Exception:
                        pass

                    if is_marked:
                        print(f"  ⏩ 跳过第 {i+1} 条 (已被油猴脚本标记)...")
                        continue

                await check_pause()
                print(f"\n👉 正在处理第 {i+1}/{count} 条...")
                await list_page.bring_to_front()

                await asyncio.sleep(random.uniform(1.0, 3.0))

                need_manual_check = False
                pause_reason = ""

                try:
                    current_order = order_locators.nth(i)

                    # --- 1. 打开第一层（订单页） ---
                    async with list_page.context.expect_page(timeout=10000) as page1_info:
                        await human_click(list_page, current_order)
                    detail_page1 = await page1_info.value
                    await detail_page1.wait_for_load_state("domcontentloaded")
                    print("  ✅ 第一层")
                    await human_delay(1.5, 4.0)

                    # ==========================================
                    # 🌟 核心：在第一层页面提取信息并判断
                    # ==========================================
                    if CHECK_PHONE:
                        print("  🔍 在第一层检测 收货人 与 订单留言...")
                        await asyncio.sleep(1.0)

                        receiver_val = ""
                        remark_text = ""

                        target_frame = detail_page1
                        if await detail_page1.locator("xpath=//span[contains(text(), '收货人')]").count() == 0:
                            for f in detail_page1.frames:
                                try:
                                    if await f.locator("xpath=//span[contains(text(), '收货人')]").count() > 0:
                                        target_frame = f
                                        break
                                except Exception:
                                    pass

                        try:
                            rec_loc = target_frame.locator("xpath=//span[contains(text(), '收货人')]/following-sibling::span[1]")
                            if await rec_loc.count() > 0:
                                receiver_val = (await rec_loc.first.inner_text(timeout=3000)).strip()

                            rem_loc = target_frame.locator("xpath=//span[contains(text(), '订单留言')]/following-sibling::span[1]")
                            if await rem_loc.count() > 0:
                                remark_text = (await rem_loc.first.inner_text(timeout=3000)).strip()
                        except Exception as e:
                            print(f"  ⚠️ 提取超时，默认放行: {e}")

                        print(f"  [收货人] 提取到: '{receiver_val}'")
                        print(f"  [订单留言] 提取到: '{remark_text}'")

                        if receiver_val and PHONE_PATTERN.search(receiver_val):
                            need_manual_check = True
                            pause_reason = f"收货人字段包含号码: {receiver_val}"

                        if not need_manual_check and remark_text:
                            remark_phones = PHONE_PATTERN.findall(remark_text)
                            has_sales = "销售" in remark_text

                            if len(remark_phones) >= 2:
                                need_manual_check = True
                                pause_reason = f"订单留言包含多个号码 ({len(remark_phones)}个): {remark_phones}"
                            elif len(remark_phones) == 1:
                                if not has_sales:
                                    need_manual_check = True
                                    pause_reason = f"订单留言只含1个号码，且无销售字样: {remark_phones}"
                                else:
                                    print("  ✅ 订单留言只有1个号码且带有【销售】字样，自动跳过。")
                            else:
                                print("  ✅ 订单留言无号码，自动跳过。")

                    # --- 2. 进入第二层去点击电话 ---
                    order_link = detail_page1.locator('a[title="点击跳转到订单详情页"]')
                    async with detail_page1.context.expect_page(timeout=10000) as page2_info:
                        await human_click(detail_page1, order_link.first)
                    detail_page2 = await page2_info.value
                    await detail_page2.wait_for_load_state("domcontentloaded")
                    print("  ✅ 第二层")

                    await human_distraction(detail_page2)
                    await human_delay(1.5, 4.5)

                    tel_locator = detail_page2.locator('a[onclick$=",2)"]')
                    if await tel_locator.count() > 0:
                        print("  📞 点击电话 x2...")
                        await human_click(detail_page2, tel_locator.first)
                        await human_delay(1.0, 3.0)
                        await human_click(detail_page2, tel_locator.first)
                        await human_delay(0.5, 2.0)

                    if need_manual_check:
                        print(f"\n🚨🚨🚨 触发暂停规则！原因: {pause_reason}")
                        print("👉 页面已保留，请人工核对。核对完毕后按 F9 继续脚本。")
                        await detail_page2.bring_to_front()
                        is_paused = True
                        await check_pause()
                        print("▶️ 人工核对完毕，继续...")

                except Exception as e:
                    print(f"  ❌ 出错: {e}")

                finally:
                    for ctx in browser.contexts:
                        for pg in ctx.pages:
                            if pg != list_page and not pg.is_closed():
                                try: await pg.close()
                                except Exception: pass

                    if not list_page.is_closed():
                        await list_page.bring_to_front()
                    save_progress(page_num, i + 1, fingerprint)

                    processed_count += 1
                    if random.random() < 0.05:
                        fish_time = random.randint(15, 40)
                        print(f"\n☕ 【碰巧喝口水】处理了 {processed_count} 单，随机休息 {fish_time} 秒...")
                        await asyncio.sleep(fish_time)
                    else:
                        await asyncio.sleep(random.uniform(1.0, 3.0))

            await check_pause()
            print("\n--- 准备翻页 ---")

            prev_first_order = ""
            try:
                if await order_locators.count() > 0:
                    prev_first_order = await order_locators.first.inner_text()
            except Exception: pass

            success = await turn_page(list_page, page_num + 1)

            if success:
                await asyncio.sleep(random.uniform(3.0, 5.0))
                new_first_order = ""
                try:
                    new_loc = await get_orders_locator(list_page, only_unmarked=False)
                    if await new_loc.count() > 0:
                        new_first_order = await new_loc.first.inner_text()
                except Exception: pass

                if new_first_order == prev_first_order and new_first_order != "":
                    print("🎉 到达最后一页！")
                    clear_progress()
                    break

                print(f"✅ 已翻至第 {page_num + 1} 页")
                page_num += 1
                start_index = 0
                save_progress(page_num, 0, fingerprint)
            else:
                print("🎉 无法翻页，执行完毕！")
                clear_progress()
                break

if __name__ == "__main__":
    print("💡 提示：运行期间按【F9】键可以随时暂停或继续脚本。")
    asyncio.run(main())