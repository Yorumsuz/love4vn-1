import sys
import asyncio
import aiohttp
from urllib.parse import urlparse, parse_qs
import json
import platform
import re
from collections import defaultdict
import pytz
from typing import List, Tuple, Dict, Set, Optional
import datetime

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class GetChannels:
    def __init__(self, url: str = None, host: str = None, port: int = None, 
                 username: str = None, password: str = None):
        if url:
            self.url = url
            self.host, self.port, self.username, self.password = self.parse_url()
        else:
            self.url = None
            self.host = host
            self.port = port or 80
            self.username = username
            self.password = password

        # Cấu hình múi giờ
        self.timezone_mapping = {
            'UK': 'Europe/London',
            'BST': 'Europe/London',
            'GMT': 'GMT',
            'ET': 'America/New_York',
            'EST': 'America/New_York',
            'EDT': 'America/New_York',
            'CT': 'America/Chicago',
            'PT': 'America/Los_Angeles'
        }
        self.vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
        
        # Danh sách từ khóa lọc
        self.sport_keywords = ["SPORT", "SPORTS", "Thể thao", "LIVE", "Live", "Spor", "Sport", "Matches", "MATCHES", "Direct", "DIRECT", "Event", "EVENT", "Events", "EVENTS", "Hub Premier", "DAZN (UK)", "EPL", "Football", "La Liga", "UEFA", "Premier League", "Golf", "Tennis"]
        self.banned_keywords = ["Live Cam", "LIVECAM", "Webcam", "CAMERA", "Cam", "CAM", "camera", "cam", "BETTING",  "Betting"]
        self.unwanted_sports = ["CRICKET", "RUGBY", "NHL", "BASEBALL", "UFC", "MMA", "Cric", "CKT", "RUGY", "BASEBALL", "HOCKEY", "NFL", "NRL", "AHL", "ARL", "Events/PPV", "Matchroom", "STAN EVENT", "Speedway", "Clubber", "FITETV", "SKWEEK", "GAAGO", "EFL", "MLS Pass", "National League", "PDC", "ARL", "SPFL", "Wrestling", "WWE", "MOLA", "NCAAB", "NCAAF", "OHL", "JHL", "STAN", "Supercross", "WHL", "WNBA", "IN/PK", "REPLAY", "Flo", "Dirtvision", "Ligue 1 Pass", "Malaysia", "Saudi Arabia", "Pool", "STARZPLAY", "Pool", "FANDUEL", "NIFL", "XFL"]
        self.low_quality_keywords = ["SD", "480p", "360p", "240p", "LQ", "LOW", "LOWQ", "SQ", "STD"]
        
        # Bổ sung pattern mới để xử lý các định dạng thời gian
        self.date_formats = [
            r'(\d{1,2})/(\d{1,2})',  # DD/MM
            r'(\d{1,2})\.(\d{1,2})\.',  # DD.MM.
            r'(\d{1,2})\s+(\w{3,})',  # DD Month
            r'(\w{3,})\s+(\d{1,2})',  # Month DD
        ]

    def parse_url(self) -> Tuple[str, int, str, str]:
        if not self.url.startswith("http"):
            raise ValueError("URL phải bắt đầu bằng http hoặc https")

        parsed = urlparse(self.url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        
        # Lấy thông tin đăng nhập từ URL hoặc query string
        username = parsed.username
        password = parsed.password
        
        if not username or not password:
            qs = parse_qs(parsed.query)
            username = qs.get("username", [None])[0]
            password = qs.get("password", [None])[0]

        if not username or not password:
            raise ValueError("Không tìm thấy username hoặc password trong URL")

        return host, port, username, password

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": f"http://{self.host}/"
            }
            async with session.get(url, headers=headers, timeout=20) as response:
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError as e:
            print(f"⚠️ Lỗi khi truy cập {url}: {str(e)}")
            return ""
        except asyncio.TimeoutError:
            print(f"⌛ Timeout khi truy cập {url}")
            return ""

    async def get_server_info(self) -> Dict:
        api_url = f"http://{self.host}:{self.port}/player_api.php?username={self.username}&password={self.password}"
        async with aiohttp.ClientSession() as session:
            response = await self.fetch(session, api_url)
            try:
                return json.loads(response) if response else {}
            except json.JSONDecodeError:
                print(f"❌ Không thể parse JSON từ: {api_url}")
                return {}

    def _format_expiry(self, timestamp: int) -> str:
        if not timestamp or timestamp == 0:
            return "Vĩnh viễn"
        try:
            return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "Không xác định"

    async def get_sports_channels(self) -> List[Tuple[str, str, str, str, str]]:
        base_url = f"http://{self.host}:{self.port}"
        sport_channels = []

        async with aiohttp.ClientSession() as session:
            try:
                # Lấy danh mục kênh
                cat_url = f"{base_url}/player_api.php?username={self.username}&password={self.password}&action=get_live_categories"
                cat_resp = await self.fetch(session, cat_url)
                if not cat_resp:
                    print(f"❌ Không nhận được dữ liệu từ {cat_url}")
                    return []
                
                try:
                    categories = json.loads(cat_resp)
                except json.JSONDecodeError:
                    print(f"❌ Dữ liệu không phải JSON từ {cat_url}")
                    return []
                
                cat_map = {c["category_id"]: c["category_name"] for c in categories}

                # Lấy danh sách kênh
                stream_url = f"{base_url}/player_api.php?username={self.username}&password={self.password}&action=get_live_streams"
                stream_resp = await self.fetch(session, stream_url)
                if not stream_resp:
                    print(f"❌ Không nhận được dữ liệu từ {stream_url}")
                    return []
                
                try:
                    streams = json.loads(stream_resp)
                except json.JSONDecodeError:
                    print(f"❌ Dữ liệu không phải JSON từ {stream_url}")
                    return []

                print(f"  Số danh mục: {len(categories)}, Số kênh: {len(streams)}")

                for s in streams:
                    cat_id = s.get("category_id")
                    cat_name = cat_map.get(cat_id, "Unknown")
                    name = s.get("name", "").strip()
                    stream_id = s.get("stream_id", "")
                    logo = s.get("stream_icon", "")

                    if not name or not stream_id:
                        continue

                    # Kiểm tra các điều kiện lọc
                    if self._should_skip_channel(name, cat_name):
                        continue

                    try:
                        # Xử lý tên kênh (chuyển đổi thời gian)
                        processed_name = self._process_channel_name(name)
                    except Exception as e:
                        print(f"⚠️ Lỗi khi xử lý tên kênh '{name}': {str(e)}")
                        processed_name = name  # Sử dụng tên gốc nếu có lỗi

                    # Tạo entry cho kênh
                    tvg_id = re.sub(r'\W+', '', processed_name.lower())
                    extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{processed_name}" tvg-logo="{logo}" group-title="{cat_name}",{processed_name}'
                    stream_url = f"{base_url}/live/{self.username}/{self.password}/{stream_id}.ts"

                    sport_channels.append((extinf, stream_url, cat_name, processed_name, stream_id))

            except Exception as e:
                print(f"❌ Lỗi khi xử lý {self.host}: {str(e)}")

        return sport_channels

    def _should_skip_channel(self, name: str, category: str) -> bool:
        """Kiểm tra xem có nên bỏ qua kênh này không"""
        name_lower = name.lower()
        cat_lower = category.lower()

        # Bỏ qua nếu thuộc danh mục không mong muốn
        if any(kw.lower() in cat_lower for kw in self.banned_keywords):
            return True

        # Bỏ qua nếu là môn thể thao không mong muốn (kiểm tra cả tên và category)
        if (any(sport.lower() in name_lower for sport in self.unwanted_sports) or
            any(sport.lower() in cat_lower for sport in self.unwanted_sports)):
            return True

        # Bỏ qua nếu chất lượng thấp
        if any(kw.lower() in name_lower for kw in self.low_quality_keywords):
            return True

        # Chỉ giữ lại kênh thể thao
        if not any(kw.lower() in cat_lower for kw in self.sport_keywords):
            return True

        return False

    def _convert_time(self, time_str: str, ampm: Optional[str] = None) -> Tuple[int, int]:
        """Chuyển đổi thời gian AM/PM sang 24h format"""
        time_str = time_str.strip()
        if ':' in time_str:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            hour = int(time_str)
            minute = 0
            
        if ampm:
            ampm = ampm.upper()
            if ampm == "PM" and hour < 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
                
        return hour, minute

    def _adjust_for_timezone(self, hour: int, minute: int) -> Tuple[int, int, int]:
        """Điều chỉnh thời gian cho múi giờ Việt Nam (+6 giờ)"""
        # Luôn cộng 6 giờ
        new_hour = hour + 6
        day_adjust = 0
        
        # Điều chỉnh nếu vượt quá 24h
        if new_hour >= 24:
            new_hour -= 24
            day_adjust = 1
            
        return new_hour, minute, day_adjust

    def _format_time(self, hour: int, minute: int) -> str:
        """Định dạng thời gian thành chuỗi HH:MM"""
        return f"{hour:02d}:{minute:02d}"

    def _process_time_and_date(self, time_str: str, date_str: str, ampm: Optional[str] = None) -> Tuple[str, str]:
        """Xử lý cả thời gian và ngày tháng cùng lúc, trả về thời gian và ngày mới"""
        try:
            # Chuyển đổi thời gian
            hour, minute = self._convert_time(time_str, ampm)
            new_hour, new_minute, day_adjust = self._adjust_for_timezone(hour, minute)
            new_time = self._format_time(new_hour, new_minute)
            
            # Xử lý ngày tháng
            new_date = date_str
            for fmt in self.date_formats:
                try:
                    match = re.search(fmt, date_str)
                    if match:
                        groups = match.groups()
                        day = int(groups[0])
                        month_str = groups[1]
                        
                        # Xử lý tên tháng
                        month_dict = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                     'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                        if month_str.isdigit():
                            month = int(month_str)
                        else:
                            month = month_dict.get(month_str[:3], datetime.datetime.now().month)
                        
                        # Tính toán ngày mới
                        new_day = day + day_adjust
                        year = datetime.datetime.now().year
                        
                        # Kiểm tra nếu vượt quá số ngày trong tháng
                        try:
                            datetime.datetime(year, month, new_day)
                        except ValueError:
                            new_day = 1
                            month += 1
                            if month > 12:
                                month = 1
                                year += 1
                        
                        # Format lại ngày tháng
                        if fmt == self.date_formats[0]:  # DD/MM
                            new_date = f"{new_day}/{month}"
                        elif fmt == self.date_formats[1]:  # DD.MM.
                            new_date = f"{new_day}.{month}."
                        elif fmt == self.date_formats[2]:  # DD Month
                            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                            new_month_name = month_names[month - 1]
                            new_date = f"{new_day} {new_month_name}"
                        elif fmt == self.date_formats[3]:  # Month DD
                            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                            new_month_name = month_names[month - 1]
                            new_date = f"{new_month_name} {new_day}"
                        break
                except:
                    continue
            
            return new_time, new_date
        except Exception as e:
            print(f"⚠️ Lỗi xử lý thời gian và ngày: {str(e)}")
            return time_str, date_str

    def _process_channel_name(self, name: str) -> str:
        """Xử lý tên kênh, chuyển đổi thời gian sang giờ Việt Nam"""
        # Xử lý các trường hợp đặc biệt như "FRIENDLY 03: Girona 19:00 Wolves 03/08"
        special_cases = [
            # Định dạng: "Girona 19:00 Wolves 03/08"
            (r'(.+?)(\d{1,2}:\d{2})(.+?)(\d{1,2}/\d{1,2})', 
             lambda m: f"{m.group(1)}{self._process_time_and_date(m.group(2), m.group(4))[0]}{m.group(3)}{self._process_time_and_date(m.group(2), m.group(4))[1]} (VN)"),
            
            # Định dạng: "Newcastle 12:00 Tottenham 03/08"
            (r'(.+?)(\d{1,2}:\d{2})(.+?)(\d{1,2}/\d{1,2})', 
             lambda m: f"{m.group(1)}{self._process_time_and_date(m.group(2), m.group(4))[0]}{m.group(3)}{self._process_time_and_date(m.group(2), m.group(4))[1]} (VN)")
        ]

        # Xử lý các pattern thông thường
        time_patterns = [
            # Định dạng thời gian kép: 19:00 -- 22:00
            (r'(\d{1,2}:\d{2})\s*--\s*(\d{1,2}:\d{2})', 
             lambda m: f"{self._process_time_and_date(m.group(1), '')[0]} -- {self._process_time_and_date(m.group(2), '')[0]} (VN)"),
            
            # Định dạng thời gian đơn giản với múi giờ
            (r'(\d{1,2}:\d{2})\s+([A-Z]{2,4})', 
             lambda m: f"{self._process_time_and_date(m.group(1), '')[0]} (VN)"),
            
            # Định dạng thời gian với AM/PM
            (r'(\d{1,2}:\d{2})\s*(am|pm)\b', re.IGNORECASE, 
             lambda m: f"{self._process_time_and_date(m.group(1), '', m.group(2))[0]} (VN)"),
            
            # Định dạng ngày tháng: 03/08
            (r'(\d{1,2}/\d{1,2})', 
             lambda m: f"{m.group(1)} (VN)"),
            
            # Định dạng thời gian đơn giản
            (r'\b(\d{1,2}:\d{2})\b', 
             lambda m: f"{self._process_time_and_date(m.group(1), '')[0]} (VN)")
        ]

        # Thử xử lý các trường hợp đặc biệt trước
        for pattern, handler in special_cases:
            try:
                if re.search(pattern, name):
                    return re.sub(pattern, lambda m: handler(m), name)
            except:
                continue

        # Xử lý các pattern thông thường
        for pattern in time_patterns:
            flags = re.IGNORECASE if len(pattern) == 3 else 0
            regex = re.compile(pattern[0], flags) if len(pattern) > 2 else re.compile(pattern[0])
            handler = pattern[1] if len(pattern) < 3 else pattern[2]
            
            try:
                if regex.search(name):
                    return regex.sub(lambda m: handler(m), name)
            except:
                continue

        return name

async def process_server(server_data: Tuple[str, Tuple]) -> Tuple[List[Tuple[str, str, str, str, str]], int]:
    try:
        if server_data[0] == "url":
            fetcher = GetChannels(url=server_data[1])
        else:
            host, port, username, password = server_data[1]
            fetcher = GetChannels(host=host, port=port, username=username, password=password)

        print(f"\n🔍 Đang xử lý server: {fetcher.host}:{fetcher.port}")
        
        # Hiển thị thông tin server
        server_info = await fetcher.get_server_info()
        if server_info:
            user_info = server_info.get("user_info", {})
            print(f"👤 User: {user_info.get('username', '?')}")
            print(f"📶 Active connections: {user_info.get('active_cons', '?')}/{user_info.get('max_connections', '?')}")
            print(f"⏳ Expiry: {fetcher._format_expiry(user_info.get('exp_date'))}")

        # Lấy kênh thể thao
        channels = await fetcher.get_sports_channels()
        print(f"✅ Tìm thấy {len(channels)} kênh thể thao phù hợp")
        return channels, len(channels)

    except Exception as e:
        print(f"❌ Lỗi khi xử lý server: {str(e)}")
        return [], 0

def parse_server_list(lines: List[str]) -> List[Tuple]:
    servers = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if line.startswith("http"):
            servers.append(("url", line))
        elif "," in line:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                try:
                    port = int(parts[1])
                    servers.append(("creds", (parts[0], port, parts[2], parts[3])))
                except ValueError:
                    print(f"⚠️ Port không hợp lệ: {line}")
    return servers

def generate_sorted_playlist(channels: List[Tuple]) -> List[str]:
    # Nhóm kênh theo category
    group_channels = defaultdict(list)
    for extinf, stream_url, group, name in channels:
        group_channels[group].append((extinf, stream_url, name))

    # Từ khóa xác định group sự kiện trực tiếp
    live_keywords = ["LIVE", "TRỰC TIẾP", "EVENT", "MATCH", "GAME", "DIRECT"]
    
    # Phân loại group: sự kiện trực tiếp và thông thường
    live_groups = []
    other_groups = []
    
    for group in group_channels:
        group_upper = group.upper()
        if any(kw in group_upper for kw in live_keywords):
            live_groups.append(group)
        else:
            other_groups.append(group)
    
    # Hàm sắp xếp group: ưu tiên số rồi đến chữ
    def sort_group(groups):
        with_numbers = []
        without_numbers = []
        
        for group in groups:
            numbers = re.findall(r'\d+', group)
            if numbers:
                with_numbers.append((int(numbers[0]), group))
            else:
                without_numbers.append(group)
        
        with_numbers.sort(key=lambda x: x[0])
        without_numbers.sort(key=str.lower)
        
        return [item[1] for item in with_numbers] + without_numbers
    
    # Sắp xếp từng loại group
    sorted_live = sort_group(live_groups)
    sorted_other = sort_group(other_groups)
    
    # Kết hợp: group sự kiện trực tiếp lên đầu
    sorted_groups = sorted_live + sorted_other

    # Tạo playlist
    playlist = ["#EXTM3U"]
    for group in sorted_groups:
        for extinf, stream_url, _ in sorted(group_channels[group], key=lambda x: x[2].lower()):
            playlist.extend([extinf, stream_url])

    return playlist

async def main_async():
    try:
        # Đọc danh sách server từ file
        with open("Xtream_List.txt", "r") as f:
            servers = parse_server_list(f.readlines())
    except FileNotFoundError:
        print("❌ Không tìm thấy file Xtream_List.txt")
        return

    if not servers:
        print("❌ Không có server hợp lệ trong file")
        return

    all_channels = []
    channel_keys = set()
    total_channels = 0

    # Xử lý từng server
    tasks = [process_server(server) for server in servers]
    results = await asyncio.gather(*tasks)

    for channels, count in results:
        total_channels += count
        for channel in channels:
            extinf, stream_url, group, name, stream_id = channel
            channel_key = f"{group}_{name}_{stream_id}"
            if channel_key not in channel_keys:
                channel_keys.add(channel_key)
                all_channels.append((extinf, stream_url, group, name))

    # Sắp xếp kênh
    sorted_playlist = generate_sorted_playlist(all_channels)

    # Lưu file
    output_file = "Xtreamlist_Sports_All.m3u"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted_playlist))

    print(f"\n🎉 Hoàn thành! Đã lưu {len(all_channels)} kênh vào {output_file}")

def main():
    try:
        # Kiểm tra và cài đặt pytz nếu cần
        try:
            import pytz
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pytz"])
            import pytz

        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng chương trình")
    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {str(e)}")

if __name__ == "__main__":
    main()
