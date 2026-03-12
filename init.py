import asyncio
import threading
import datetime
import customtkinter as ctk
from playwright.async_api import async_playwright
try:
    from playwright_stealth.stealth import stealth as apply_stealth
except ImportError:
    # 환경에 따라 경로가 다를 수 있으므로 예외 처리를 추가합니다.
    from playwright_stealth import stealth as apply_stealth
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# 테마 설정
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- [커스텀 위젯: 숫자 전용 스핀박스] ---
class IntSpinbox(ctk.CTkFrame):
    def __init__(self, *args, width: int = 150, height: int = 32, step_size: int = 1, default_value: int = 0, **kwargs):
        super().__init__(*args, width=width, height=height, **kwargs)

        self.step_size = step_size
        self.grid_columnconfigure((0, 2), weight=0)
        self.grid_columnconfigure(1, weight=1)

        vcmd = (self.register(self._validate), '%P')

        self.subtract_button = ctk.CTkButton(self, text="-", width=height-6, height=height-6,
                                               command=self.subtract_button_callback)
        self.subtract_button.grid(row=0, column=0, padx=(3, 0), pady=3)

        self.entry = ctk.CTkEntry(self, width=width-(2*height), height=height-6, border_width=0, 
                                  justify="center", validate="key", validatecommand=vcmd)
        self.entry.grid(row=0, column=1, columnspan=1, padx=3, pady=3, sticky="ew")

        self.add_button = ctk.CTkButton(self, text="+", width=height-6, height=height-6,
                                            command=self.add_button_callback)
        self.add_button.grid(row=0, column=2, padx=(0, 3), pady=3)

        self.entry.insert(0, str(default_value))
   
    def _validate(self, value):
        if value == "" or value.isdigit():
            return True
        return False

    def add_button_callback(self):
        try:
            value = int(self.entry.get()) + self.step_size
            self.entry.delete(0, "end")
            self.entry.insert(0, value)
        except ValueError:
            self.entry.insert(0, "0")

    def subtract_button_callback(self):
        try:
            current_val = int(self.entry.get())
            if current_val > 0:
                value = current_val - self.step_size
                self.entry.delete(0, "end")
                self.entry.insert(0, value)
        except ValueError:
            self.entry.insert(0, "0")

    def get(self) -> int:
        try:
            return int(self.entry.get())
        except ValueError:
            return 0

# --- [메인 애플리케이션 창] ---
class CrawlerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Market Scraper Pro v1.1")
        self.geometry("1100x750")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ------------------ [좌측 사이드바] ------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="MARKET BOT", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 20))

        self.user_id = ctk.CTkEntry(self.sidebar_frame, placeholder_text="아이디")
        self.user_id.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.user_pw = ctk.CTkEntry(self.sidebar_frame, placeholder_text="비밀번호", show="*")
        self.user_pw.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.market_label = ctk.CTkLabel(self.sidebar_frame, text="대상 마켓 선택", font=ctk.CTkFont(size=13, weight="bold"))
        self.market_label.grid(row=3, column=0, padx=20, pady=(15, 5), sticky="w")
        self.market_option = ctk.CTkOptionMenu(self.sidebar_frame, values=["도매꾹", "아마존", "이베이", "쿠팡"])
        self.market_option.grid(row=4, column=0, padx=20, pady=5, sticky="ew")

        self.sp_label = ctk.CTkLabel(self.sidebar_frame, text="시작 페이지", font=ctk.CTkFont(size=13))
        self.sp_label.grid(row=5, column=0, padx=20, pady=(15, 0), sticky="w")
        self.start_page_spinbox = IntSpinbox(self.sidebar_frame, default_value=1)
        self.start_page_spinbox.grid(row=6, column=0, padx=20, pady=5, sticky="ew")

        self.mc_label = ctk.CTkLabel(self.sidebar_frame, text="최대 수집 개수 (0: 무제한)", font=ctk.CTkFont(size=13))
        self.mc_label.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        self.max_count_spinbox = IntSpinbox(self.sidebar_frame, default_value=100, step_size=10)
        self.max_count_spinbox.grid(row=8, column=0, padx=20, pady=5, sticky="ew")

        self.path_btn = ctk.CTkButton(self.sidebar_frame, text="결과 저장 폴더 선택", fg_color="transparent", border_width=1)
        self.path_btn.grid(row=9, column=0, padx=20, pady=20, sticky="ew")

        self.proxy_label = ctk.CTkLabel(self.sidebar_frame, text="Tor Proxy: Waiting...", text_color="#e67e22")
        self.proxy_label.grid(row=10, column=0, padx=20, pady=10)

        # ------------------ [우측 메인 구역] ------------------
        self.main_frame = ctk.CTkFrame(self, corner_radius=15)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1)

        self.url_entry = ctk.CTkEntry(self.main_frame, placeholder_text="도매꾹 카테고리 URL을 입력하세요", height=40)
        self.url_entry.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        # 테스트용 주소 미리 입력
        self.url_entry.insert(0, "https://domeggook.com/main/item/itemList.php?cat=08_04_00_00")

        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.grid(row=1, column=0, padx=20, pady=0, sticky="ew")
        
        self.start_btn = ctk.CTkButton(self.btn_frame, text="수집 시작", width=120, fg_color="#2ecc71", hover_color="#27ae60", command=self.start_crawling)
        self.start_btn.grid(row=0, column=0, padx=5)
        
        self.pause_btn = ctk.CTkButton(self.btn_frame, text="일시 중지", width=120, fg_color="#f1c40f", hover_color="#f39c12", text_color="black")
        self.pause_btn.grid(row=0, column=1, padx=5)
        
        self.stop_btn = ctk.CTkButton(self.btn_frame, text="강제 종료", width=120, fg_color="#e74c3c", hover_color="#c0392b")
        self.stop_btn.grid(row=0, column=2, padx=5)

        self.mode_btn = ctk.CTkSegmentedButton(self.btn_frame, values=["일반", "상세포함", "이미지만"])
        self.mode_btn.set("일반")
        self.mode_btn.grid(row=0, column=3, padx=10)

        self.log_textbox = ctk.CTkTextbox(self.main_frame, font=("Consolas", 12))
        self.log_textbox.grid(row=2, column=0, padx=20, pady=20, sticky="nsew")
        self.log_textbox.insert("0.0", "--- 시스템 로그 시작 ---\n")
        
        self.is_running = False

    def log(self, message):
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_textbox.insert("end", f"[{current_time}] {message}\n")
        self.log_textbox.see("end")

    def start_crawling(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.configure(text="수집 중...", state="disabled")
            # [수정됨] .समर्थ크_start() 오타를 .start()로 변경
            threading.Thread(target=self._run_async_crawler, daemon=True).start()

    def _run_async_crawler(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.run_crawler())

    async def run_crawler(self):
        base_url = self.url_entry.get()
        start_page = self.start_page_spinbox.get()
        max_items = self.max_count_spinbox.get()
        collected_count = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            # [수정됨] stealth_async -> stealth
            try:
                await apply_stealth(page)
            except Exception:
                # 만약 여기서도 에러가 난다면 아예 스킵하고 진행합니다.
                self.log("주의: Stealth 모드 적용 실패 (무시하고 진행)")

            current_page = start_page
            
            while collected_count < max_items:
                parsed_url = urlparse(base_url)
                params = parse_qs(parsed_url.query)
                params['pg'] = [str(current_page)]
                new_query = urlencode(params, doseq=True)
                target_url = urlunparse(parsed_url._replace(query=new_query))

                self.log(f"{current_page}페이지 분석 중...")
                await page.goto(target_url, wait_until="domcontentloaded")
                
                items = await page.query_selector_all("ol.lItemList > li")
                
                if not items:
                    self.log("데이터를 더 이상 찾을 수 없습니다.")
                    break

                for item in items:
                    if collected_count >= max_items: break
                    
                    try:
                        title_el = await item.query_selector(".title")
                        title = await title_el.inner_text() if title_el else "제목없음"
                        
                        price_el = await item.query_selector(".amt b")
                        price = await price_el.inner_text() if price_el else "0"
                        
                        collected_count += 1
                        self.log(f"[{collected_count}] {title[:15]}... | {price}원")
                        
                    except Exception:
                        continue
                
                current_page += 1
                await asyncio.sleep(1)

            await browser.close()
            self.log(f"총 {collected_count}개 수집 완료.")
            self.is_running = False
            self.start_btn.configure(text="수집 시작", state="normal")

if __name__ == "__main__":
    app = CrawlerApp()
    app.mainloop()