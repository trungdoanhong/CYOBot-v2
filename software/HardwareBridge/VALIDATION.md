# Kiểm chứng ngày 2026-10-07

Đã nạp và kiểm tra trên **một CYOBrain thật**, ESP32-S3, MAC `3c:84:27:f3:d0:5c`, cổng COM6, Wi-Fi NHA PINK, IP `192.168.1.8`. Firmware được khởi động lại sau khi nạp; nhận diện PCA9685 và LSM6DSL thành công. Sau khi khởi tạo, firmware đọc lại thanh ghi để xác nhận cả 16 kênh đều có bit FULL_OFF.

Binary SHA256: `0b2337c5f9d855be1303f522ee167098b8a7ffb2a3a492437d6865acb3f7dd12`.

Build PlatformIO thành công: flash ứng dụng 691,585 byte; RAM tĩnh 43,768 byte. Esptool xác nhận hash dữ liệu đã ghi vào flash. 13 unit test Python đạt, gồm giao thức, số thứ tự quay vòng, hiệu chỉnh, dáng đi và định tuyến trạng thái của 30 robot giả lập trong bộ nhớ.

`python tools/smoke_board.py --ip 192.168.1.8` đã kiểm tra trực tiếp firmware:

- Frame trùng, ngược thứ tự và sai độ dài không được áp dụng.
- Client thứ hai và gói từ sai cổng nguồn không chiếm quyền điều khiển.
- Phiên hết hạn sau 250 ms; challenge thay đổi; gói CLAIM/FRAME thuộc phiên cũ bị bỏ.
- Phiên mới cần được tạo chủ động; giá trị PWM trước/sau hết hạn giữ nguyên.
- Lệnh OFF có phản hồi xác nhận.

Các phép thử dùng toàn bộ giá trị PWM bằng 0, không yêu cầu servo chuyển động. Chính sách giữ PWM đã được kiểm tra với trạng thái tắt; chưa thử giữ tư thế có tải, dáng đi thực tế hay ngắt nguồn router trong lần kiểm chứng này.

Mỗi lượt benchmark dưới đây dài 10 giây, dùng đồng hồ `perf_counter` trên máy tính Windows. Cùng lúc, firmware đọc IMU và gửi telemetry. Thư mục `reports/` chứa JSON thô của các lượt đo trên máy này.

| Tần suất gửi | Gói gửi | Gói hợp lệ nhận | Lần ghi PWM | Lần ghi PWM/giây | RTT trung vị | RTT p95 |
|---|---:|---:|---:|---:|---:|---:|
| 100 Hz | 1.000 | 1.000 | 994 | 99,4 | 19,90 ms | 29,78 ms |
| 200 Hz | 2.000 | 1.999 | 1.843 | 184,3 | 14,92 ms | 20,25 ms |
| 400 Hz | 4.000 | 3.982 | 2.264 | 226,4 | 12,45 ms | 20,04 ms |

RTT được lấy từ các mẫu telemetry xác nhận số thứ tự đã ghi PWM; gồm độ trễ mạng hai chiều, lịch telemetry và thời điểm host đọc socket. Đây không phải số đo độ trễ một chiều hoặc chuyển động cơ khí. Lượt ghi I²C cuối ở mỗi lần thử mất 1.730 / 1.731 / 1.669 microsecond.

Gói hợp lệ nhận nhiều hơn số lượt ghi vì firmware giữ frame mới nhất trong mỗi lượt xử lý. Tần suất PWM vật lý vẫn theo prescaler cũ (danh định khoảng 54 Hz). Mức 400 Hz là một bài đo tải, không phải bảo đảm điều khiển cơ khí 400 Hz hay giới hạn tuyệt đối của hệ thống.

Tại cuối phép đo, không có fault; IMU trả dữ liệu hợp lệ, ADC pin khoảng 7,4 V (chưa hiệu chuẩn). Discovery unicast và broadcast có đích `192.168.1.255` hoạt động. Broadcast `255.255.255.255` không tìm được robot trong cấu hình card mạng của máy này.

Chưa kiểm chứng trên hàng chục robot thật và chưa có mô hình AI được huấn luyện/tích hợp để chạy thực tế. SDK hỗ trợ quản lý theo MAC, hiệu chỉnh riêng từng robot và truyền dữ liệu theo nhóm để chuẩn bị cho bước đó.

## CYOBot Studio — 2026-10-08

21 unit test Python đạt (13 giao thức/SDK và 8 controller/HTTP). Test mới dùng mạch giả, kiểm tra kết nối không bật kênh, điều khiển đủ 16 kênh, giới hạn góc, dừng test/giữ giá trị khi heartbeat mất, dừng khi telemetry hết hạn, cô lập cửa sổ, OFF có xác nhận và kiểm tra token/Host của server cục bộ. JavaScript qua `node --check`.

Đã mở và thao tác giao diện bằng trình duyệt ở 1440×960, 1280×720 và 390×844: mô hình WebGL, chọn khớp, test/dáng đi trong chế độ xem trước, thả nút hướng, bảng cảm biến, thanh điều khiển và nút OFF trên desktop. Không có lỗi JavaScript trong lần kiểm tra giao diện cuối.

Đã kết nối Studio tới mạch thật tại `192.168.1.8`: telemetry báo flags 45 (OWNED/PWM_OK/IMU_OK/WIFI_OK), điện áp khoảng 8,14 V, gia tốc khoảng `[0.017, -0.046, 1.013] g`, RTT mẫu khoảng 16 ms. Đã đọc cảm biến và kiểm tra OFF có xác nhận, cả 16 kênh vẫn bằng 0. Không phát lệnh làm servo thật chuyển động trong lần kiểm tra UI này; chuyển động 3D xem trước và test controller giả không thay thế kiểm tra cơ khí có tải.


## Mô hình crawler gốc — 2026-10-08

Đã thay hình học minh họa bằng URDF/STL của phiên Blender ngày 27/09/2026. Đối chiếu nguyên byte 148 file với nguồn (URDF và 147 STL); 115 visual mesh và 32 collision mesh có đầy đủ đường dẫn. Studio chỉ tải 115 visual mesh. Hash nguồn nằm trong `host/ui/robot/manifest.json`.

Đã tải mô hình trong trình duyệt, chọn khớp hông/chân, thử đủ tám khớp ở góc lệnh ±30° trong chế độ xem trước và chạy test một servo trên mô hình. Góc cập nhật theo offset/chiều trong cấu hình; khớp phụ mimic chuyển động của khớp chân. Sai số khép kín lớn nhất đo từ các điểm nối bốn thanh nhỏ hơn 0,00002 mm (sai số số học của bản URDF). Giữ nguyên màu và hình học nguồn; điều chỉnh ánh sáng, khung nhìn và marker chọn khớp để dùng trong Studio. JavaScript syntax check và tải WebGL thành công, không có lỗi console khi kiểm tra.

Các thao tác này dùng chế độ xem trước trên PC; không phát lệnh làm servo thật chuyển động. Firmware và vòng điều khiển UDP không thay đổi. Hình 3D vẫn hiển thị góc đã ra lệnh, không đo góc thực và không mô phỏng lực/va chạm.

## Nạp lại qua COM6 — 2026-10-08

Windows ban đầu không mở được COM6, báo lỗi thiết bị 31. Đã xuất bản sao driver CP210x cũ 6.7.6.2130 và cập nhật lên 11.5.0.417 từ Microsoft Update Catalog; chữ ký catalog hợp lệ của Microsoft Windows Hardware Compatibility Publisher. Sau cập nhật, esptool đọc được ESP32-S3, flash 8 MB, PSRAM 8 MB. MAC đọc từ chip là `3c:84:27:f3:d0:5c`, trùng MAC mạch đã ghi nhận trước đó; đây là xác nhận mạch đang cắm, không phải xác nhận một danh tính mới.

Đã sao lưu toàn bộ 8 MB flash trước khi ghi vào `C:\Users\manhpc\.codex\backups\CYOBot-v2\20261008-165003-3c8427f3d05c-pre-reflash\flash-before-reflash.bin`. SHA-256: `4841307d851c83e76c0f56be00511fd5e8885647d672153fc6fd7969911ebd82`. PlatformIO upload firmware HardwareBridge hiện tại qua COM6 thành công; esptool xác nhận hash các vùng đã ghi. Không thay đổi logic firmware trong lượt nạp này.

Smoke test mạch thật tại `192.168.1.8` đạt: thứ tự frame, dữ liệu sai, quyền điều khiển, hết hạn phiên 250 ms, giữ PWM, tạo phiên mới và OFF. SDK duy trì giao tiếp trực tiếp ở mức gửi 100 Hz trong 10 giây; flags 45, RTT trung vị khoảng 19,9 ms, ADC pin khoảng 8,13 V. Không yêu cầu chuyển động; cả 16 giá trị PWM bằng 0.

Studio kết nối và đọc được telemetry, duy trì đủ 72 mẫu trong khoảng 15 giây, RTT mẫu cuối 15,6 ms, IMU khoảng `[-0.0045, -0.0272, 1.0243] g`; dữ liệu thô nằm trong `reports/reflash-studio-check.json`. Tuy nhiên có lượt mất phản hồi trước phép đo và một lần ngắt sau phép đo. App vẫn tìm thấy mạch online. Chưa xác định nguyên nhân ngắt kết nối và chưa xác nhận độ ổn định dài hạn của Studio. Không phát lệnh làm servo thật chuyển động.

## Điều khiển LED — 2026-10-09

Thêm điều khiển trực tiếp 33 LED ma trận (GPIO15) và 12 LED vòng (GPIO7) với thư viện Adafruit NeoPixel 1.15.5. Đối chiếu sơ đồ PCB mặt trên (trang 6) trong PDF hexaboard/base và mã MicroPython: ma trận có 5 hàng 5–7–9–7–5, số trái → phải; vòng 0 ở phía trên, tăng theo chiều kim đồng hồ. Mẫu ký tự dùng đúng ánh xạ 5×5 của display.py sang 33 LED vật lý.

Build đạt, app flash 704,833 byte, RAM tĩnh 44,568 byte. Firmware đã nạp qua COM6, MAC `3c:84:27:f3:d0:5c`, hash các vùng ghi được esptool xác nhận. SHA-256 firmware.bin: `3d8718a04573462f23d088a0bcd5382e1879c9a16257fe5ec6edc4dc48100a58`. Bản sao app trước cập nhật: `C:\Users\manhpc\.codex\backups\CYOBot-v2\20261009-led-update\app-before-led.bin`, vùng 0x10000, 0x330000 byte; bản flash đầy đủ trước đó vẫn giữ riêng.

26 unit test Python đạt; JavaScript studio.js/leds.js syntax check đạt. Test mới kiểm tra RGB/độ dài, cô lập phiên, ACK LED ngược thứ tự không cập nhật tuổi telemetry servo, giữ nguyên mục tiêu PWM, giới hạn gửi lại và báo lỗi khi thiếu ACK. Smoke servo cũ trên mạch thật đạt sau cập nhật.

Smoke LED trên mạch thật đạt đủ 45 chỉ số với màu thấp `[6,3,1]`, xác nhận các giá trị PWM luôn bằng 0. Kiểm tra ACK của PWM/LED riêng, gói LED đến sau PWM mới vẫn nhận, gói LED trùng/sai độ dài bị bỏ, hết phiên giữ màu LED và PWM, sau đó tắt cả hai cụm. Có lần gửi đơn bị mất nên phép thử và Studio cần chờ ACK/gửi lại, không xem một lần sendto thành công là đã áp dụng.

Đã thao tác UI ở 1440×900 và 390×844: mẫu trái tim/cầu vồng, bút xóa, chọn Ma trận/Vòng/Cả hai, thanh độ sáng và bố trí hàng/vòng. Studio điều khiển mạch thật ở độ sáng 5%: 16 pixel của trái tim trên ma trận, tô đủ 12 LED vòng xanh, tắt riêng vòng giữ nguyên ma trận; phản hồi từ firmware và trạng thái PWM 16 kênh bằng 0 đã được kiểm tra. Không có phép đo quang học xác nhận màu/vị trí LED vật lý; bố trí dựa trên PCB và mã nguồn. Không thay đổi timeout phiên 250 ms hay tuyên bố đã sửa lỗi ngắt kết nối dài hạn trong lượt bổ sung LED này.

## Khắc phục ngắt kết nối — 2026-10-09

Baseline SDK trực tiếp 120 giây: 11.377 frame, không mất phiên, khoảng gửi dài nhất 38,45 ms, tuổi telemetry lớn nhất 27,14 ms (`reports/connection-baseline.json`). Baseline Studio có chẩn đoán bắt được một lần mất phiên: nhịp gửi vẫn khoảng 15 ms, nhưng received trên mạch dừng ở 6.438 trong khi telemetry vẫn tiếp tục khoảng 230 ms. Sau đó phiên 250 ms hết hạn và telemetry dừng. Boot ID giữ nguyên; diagnostics sau lỗi: reason=1, lease_expirations=1, wifi_losses=0, send_errors=0, max_loop_us=6.026, RSSI khoảng −65 dBm. Không có gói bị từ chối trước khi hết phiên. Bằng chứng lưu trong `reports/studio-connection-baseline-event.json`; chẩn đoán sau lỗi nằm trong phản hồi discovery của app.

Đây là bằng chứng gián đoạn chiều gửi tới ứng dụng trên mạch, không phải chỉ lỗi heartbeat trình duyệt. Chưa phân định được adapter/driver Windows, router hay đường nhận UDP bên dưới ứng dụng. Máy tính nối AP trên 5 GHz; không thay đổi driver Wi-Fi/router hay đổ lỗi nguồn dựa trên suy đoán. Bộ đếm lỗi/discard của adapter Windows đều bằng 0 khi đọc.

Firmware giữ thời hạn phiên 1.000 ms thay vì 250 ms để chịu gián đoạn ngắn. Studio giữ góc nếu thiếu telemetry hoặc applied_seq không tiến triển trong 100 ms, hoặc host bị chậm trên 100 ms; mất heartbeat giao diện 800 ms dừng chuyển động nhưng giữ kết nối theo dõi. Nếu mất phiên, Studio tự khám phá/claim đúng MAC, đọc PWM trên mạch, không tiếp tục dáng đi/test/mục tiêu/LED cũ. Lệnh chuyển động/LED kèm control_session để lệnh chờ từ phiên cũ không khởi động lại chuyển động. Fault phần cứng không tự reconnect; ngắt chủ động hủy retry. SDK AI vẫn dừng ở ngưỡng dữ liệu/xác nhận/suy luận 250 ms và không tự reclaim.

Thêm DIAG_QUERY/DIAGNOSTICS đọc boot, phiên, tuổi lệnh, RSSI, bộ đếm Wi-Fi/lease/send và thời gian vòng firmware. Truy vấn không gia hạn phiên, không thay PWM/LED, không làm mới telemetry trong SDK. Studio lưu lịch sử 15 giây trước sự cố ra JSONL.

Build và nạp COM6 đạt, esptool xác nhận hash vùng ghi; firmware.bin 706.288 byte, SHA-256 `31394444929744f3f124aaa59d48432a9f30864fc77ea9134728bf07cec3130d`. Bản sao tại `C:\Users\manhpc\.codex\backups\CYOBot-v2\20261009-connection-fix\firmware.bin`; backup bản LED trước đó và flash đầy đủ vẫn giữ nguyên.

33 unit test và syntax JavaScript đạt. Test bao gồm mất chiều gửi nhưng telemetry vẫn mới, giữ PWM đã xác nhận thay vì frame chưa tới mạch, reconnect từ trạng thái đang giữ/reset tắt servo, không tiếp tục chuyển động, từ chối lệnh phiên cũ, hủy retry chủ động, heartbeat trễ, chuyển quyền từ cửa sổ không hoạt động và fault không retry.

Mạch thật: smoke protocol đạt (gói trùng/sai/thứ tự/quyền/expiry/HOLD/OFF, truy vấn diagnostic liên tục vẫn hết lease). Smoke LED đạt đủ 45 pixel. `tools/soak_studio.py` chặn riêng frame PWM trong 400 ms và 1.300 ms: trường hợp ngắn giữ phiên, trường hợp dài tạo phiên mới và đọc lại PWM; heartbeat giao diện dừng 1,1 giây vẫn giữ kết nối. Các kết quả được ghi ở `reports/studio-recovery-hardware.json`. Có một lần claim ngay sau khi dừng server thất bại vì phiên cũ chưa hết hạn; thử lại sau expiry đạt, không chiếm quyền cưỡng bức.

Studio với UI thật chạy liên tục 300 giây: 2.830 mẫu HTTP, 0 mẫu mất kết nối, 0 lần reconnect, 0 lỗi đọc HTTP; telemetry age lớn nhất ở các mẫu là 19 ms. Có 4 mẫu ACK chậm trên 100 ms, tại khoảng 3,5 / 196,4–196,5 / 293,1 giây, kết nối vẫn duy trì. Bộ đếm expiry=3 (do các smoke/injection trước đó), lỗi gửi=0, Wi-Fi loss=0 và boot giữ nguyên suốt phép thử; không có expiry mới. Trạng thái cuối đã gửi 20.011 frame tính từ connect (bao gồm thời gian trước bắt đầu đo), firmware received tăng 19.153 trong cửa sổ 300 giây. Báo cáo: `reports/studio-connection-fixed-300s.json`.

Tất cả kiểm tra mạch thật yêu cầu và xác nhận 16 kênh PWM bằng 0; chưa thử servo cơ khí có tải hay đội hàng chục robot. Kết quả chứng minh phục hồi/tolerant ngắt ngắn trong phạm vi phép thử, không chứng minh mạng đã hết mất gói hoặc độ ổn định nhiều giờ. Bản cuối bổ sung giữ PWM đã xác nhận và chuyển quyền từ cửa sổ không hoạt động sau phép thử 300 giây; đã kiểm tra unit và chạy lại injection trên mạch thật trước khi khởi động app.


## Media / microSD / PCM duplex — 2026-10-09

Firmware cuối được build và nạp COM6, MAC `3c:84:27:f3:d0:5c`, esptool xác nhận hash tất cả vùng ghi. `firmware.bin` 819.264 byte; SHA-256 `17083cf29d550b6d9662fe26f6700029a7b4982d5c19bded8f85caf67c589d6c`. Bản sao: `C:/Users/manhpc/.codex/backups/CYOBot-v2/20261009-media/firmware.bin`. Bản connection-fix trước media vẫn giữ nguyên để rollback. Build RAM tĩnh 58.672 byte.

Nhận ES8311 và ES7210 trên mạch. Chân I2S, microSD và PA được đối chiếu sơ đồ; PA dùng GPIO47 (không dùng nhầm chân vật lý25). Driver Espressif được giữ nguyên và ghi hash ở SOURCE.json. Gain mic được đặt sau enable vì enable khôi phục gain mặc định. Firmware mới xử lý TCP send một phần/EAGAIN với một frame chờ tối đa 250 ms, không đóng luồng ngay ở lần send chưa đủ. Parser JSON copy chuỗi khỏi buffer stack; danh sách copy tên file trước khi đóng File, phân trang theo cả số mục lẫn dung lượng JSON. Upload tránh ghi đè cả đích và file staging đã có.

Trong một lần boot sau nạp, PCA init chưa thành công dù IMU/audio nhận được; app/SDK chặn claim đúng bằng FAULT. Đã thêm tối đa 3 lần init PCA ở startup cách nhau 20 ms, tất cả PWM vẫn FULL_OFF. Boot cuối và claim đạt. Không thêm tự phục hồi fault khi robot đang chạy và chưa chứng minh nguyên nhân điện của sự cố startup đó.

43 unit Python đạt, gồm test socket loopback chia nhỏ PCM, handshake nối ngay frame đầu, stereo RMS, volume/loa, đóng socket/thread, hàng đợi giới hạn/bỏ mic cũ, đường dẫn UTF-8/traversal, upload/download binary qua chunk, từ chối ghi đè, file truyền thiếu không được công bố, mkdir/rename/trash/restore, chặn token/cửa sổ/session cũ qua HTTP. Thẻ trong test là RAM trên PC, không thay cho thử filesystem FAT thật. Node worklet test đạt capture đúng 50 frame/s ở input44.1/48 kHz, stereo playback, queue200ms và silence khi dừng. Syntax JavaScript đạt.

Phép thử duplex 60 giây trên bản trung gian sau sửa gain/partial TCP: không mất kết nối, mic/loa hoạt động đồng thời, PWM16 kênh bằng0. Tone nhỏ1 giây được gửi; chưa có người xác nhận âm thanh nghe được hay đo chất lượng âm học. Sau sửa nhịp gửi tránh tích lũy sai số timer, bản cuối chạy 30 giây: host gửi1.500 block loa, firmware ghi nhận1.495 block tại thời điểm trả info cuối (reply/counters khác thời điểm, không phải ACK từng PCM). Mic1.542 block tại info cuối; host nhận1.574 block vào lúc chốt. `reports/media-duplex-final.json`: luôn connected, PWM0, audio.error rỗng. Counter dropped52 là tổng mic+loa SDK, trong đó mic có thể bị bỏ trong thời gian script chờ info không đọc queue; không dùng số đó để suy ra loss trên Wi-Fi. Tone ở phép thử60giây không được phát lại trong phép thử cuối30giây (volume0).

UI thật tại port8765: nối được robot; nghe mic trực tiếp, worklet không báo console error. Đã chọn và gửi file WAV thử dài1,2giây từ browser; SDK gửi60 block loa. Theo dõi live tiếp60giây đồng thời gọi remount thẻ3lần: 112 mẫuHTTP, connected/audio.active luôn true, reconnections0; mic_received tăng7.920→10.920, dropped0, audio.error rỗng. Mọi telemetry PWM đều0. Kết quả `reports/media-ui-live.json`. File/mic truyền riêng với UDP control; không chứng minh không có jitter/gói mất ở tầng mạng hoặc vận hành nhiều robot.

UI thẻ tại port8766 dùng fixture hoàn toàn giả: tạo thư mụcvoice, tải file46byte vào đúng thư mục, tải về browser và so SHA-256 nguyên byte, đổi tên, chuyển file vào thùng rác, khôi phục về root. Fixture được đóng sau thử. `reports/studio-sd-simulated.png` là hình thẻ mô phỏng. Mạch thật chưa có thẻ theo người dùng: remount báo sd_ready=false, không format. Chưa kiểm tra mount/FAT/read/write/trash thật, PC-mic permission/talk qua mic thật, chất lượng loa/mic, AEC hoặc hàng chục robot. Những phần này cần xác nhận khi có phần cứng/thiết bị đầu vào tương ứng; app và SDK đã có luồng thao tác.

## UI theo không gian làm việc — 2026-10-09

Bố cục có Đội robot / Robot / Bộ não AI. Các bảng phần cứng chuyển vào một inspector cạnh 3D, dùng tab và trạng thái chung; đã bỏ CSS lưới/overlay cũ khỏi stylesheet tính năng. Thanh phiên có Giữ/Tắt xung ở cả ba trang và trên màn hình hẹp. Không thêm điều khiển AI hoặc điều khiển đồng thời nhiều robot vào Studio.

Kiểm tra bằng browser trên app thật port8765: kết nối robot192.168.1.8; 3D gốc115mesh vẫn ready, tám góc và cơ cấu giữ nguyên. Ở1440x900 canvas x184..1060 và inspector x1060..1440 không chồng nhau. Servo/IMU/LED/audio/SD chuyển đúng bảng; cả33 điểm ma trận có chỗ đủ, bố trí vòng12 điểm giữ nguyên. Đọc IMU trực tiếp; sau ngắt mạch xóa dữ liệu/nhãn LIVE cũ. Nghe mic thật rồi chuyển Robot→AI→Đội robot vẫn có dữ liệu; thay viewport/ẩn trang dừng luồng theo cơ chế sẵn có, không tự mở lại. SD thật vẫn chưa có thẻ. Phím End/Home/trái chuyển tab đúng. Test servo chỉ chạy ở Xem trước: rời Robot dừng, trở lại nút Chạy test, không tự chạy tiếp. Không gửi chuyển động servo trong thử nghiệm UI.

Trang AI ghi rõ chưa gắn mô hình. Liên kết IMU quay về đúng bảng quan sát; dialog hướng dẫn SDK mở/đóng được. Xuất mẫuJSON qua browser thành công: schema cyobot-observation-v1,16ticks, không có token/owner/control_session. Đã kiểm tra responsive390x844 và trở về viewport thực319px, document304px cộng scrollbar, không tràn ngang. Tab công cụ đã có aria-controls/tabpanel, roving tabindex và điều hướng phím. Browser bản cuối không có console warn/error.

43 test Python và worklet PCM đạt. Test workspace Node mới đạt quyền cửa sổ, lease stale/đang nối lại, preview không giả IMU/audio/thẻ, trạng tháiSD và lỗi audio. Module syntax, nestingHTML/140ID duy nhất và dấu ngoặcCSS đạt. Không kiểm tra vận hành hàng chục robot, mô hình AI hoặc thẻ FAT thật ở lần chỉnhUI này.

Ảnh thực: reports/studio-organized-desktop.png, studio-organized-fleet.png, studio-organized-brain.png (desktop1440x900); studio-organized-mobile.png (390x844, thẻ chưa có). reports/studio-organized-state.json ghi trạng thái cuối connected/HOLD,16PWM0, audio tắt. App đã tải bản cuối và giữ mở ở trang Robot.


## 2026-10-09 — English Studio, routines and LED Studio

Scope: PC application only; no firmware flash or physical servo movement during this update.

- Six finite motion programs share `host/ui/routines.json` between the Python controller and browser preview: Ready pose, Bow, Wave, Sway, Stretch, Bounce. Calibrated limits are checked before start; non-crawler channels are preserved. Hold/watchdog/session loss cancel movement, without automatic resumption.
- Five PC-generated LED animations: scrolling text, pulsing heart, blinking face, rainbow and ring chase. The 5x5 font maps into the existing 33-pixel matrix; the ring has 12 pixels. One pending LED frame with bounded retries keeps missing LED acknowledgements from blocking servo control.
- UI labels, tooltips and PC controller/media errors are English. New English README and Developer Guide include an SDK example, physical LED indexing, custom programs, local HTTP, media and simulation-policy integration. Previous README preserved as README.vi.md.

Validation performed:

- Python unittest discovery: **53 tests passed** (6.284 s), including invalid routine options/keyframes, calibration, preserved channels, Hold, watchdog, cancellation on reconnect, LED mapping/color bounds and lost LED ACK behavior.
- Node tests: workspace ownership/stale/preview states; routine interpolation/endpoints/repeats; audio worklet resampling/queue/stop all passed.
- `python -B examples/run_routine.py wave`: terminal preview completed, with no robot connection.
- Live localhost HTTP: Developer Guide served correctly; HELLO preview returned 36 frames with 33 matrix and 12 ring pixels per frame.
- Browser acceptance in PC-only Preview: wave repeat/progress and Hold; scrolling HELLO; animated face; rainbow; invalid text rejection; keyboard Clear LEDs cancels animation. No captured browser errors or warnings.
- Desktop 1440x900 and narrow 390x844 layout checked; narrow document scrollWidth equals clientWidth (375 CSS pixels excluding scrollbar). Temporary viewport override reset afterward.
- Evidence: `reports/studio-programs-desktop.png`, `reports/studio-programs-mobile.png`, `reports/studio-effects-mobile.png`.

Limitations: new routine poses have not been mechanically validated on the assembled robot. Preview is commanded-pose visualization, not dynamics/collision simulation. No physical SD card was available. The new LED generators were checked with automated/controller and browser tests; their animation appearance was not revalidated on physical LEDs during this update. Policy Lab remains an integration overview, not an exported-model loader.


## 2026-10-09 — Portable GitHub handoff

- Private Wi-Fi build settings moved to ignored wifi.local.json; the tracked legacy robot configuration has blank Wi-Fi fields. The optional environment override and missing-settings behavior have automated tests.
- Added root setup/handoff guides, a project verification entry point and Windows/Linux CI plus a firmware build job. Removed Python bytecode from version control; kept local files intact.
- Checked a clean directory exported from the Git index: all 148 model files match the source manifest; 55 HardwareBridge and 14 legacy MicroPython tests passed, as did the three JavaScript checks. Exported URDF bytes are preserved explicitly across platforms.
- Local PlatformIO build succeeded: 818,893 bytes application flash, 58,672 bytes static RAM. No board was flashed during repository preparation.
- Scanned the staged publication for the current private Wi-Fi password and common private-key/token signatures: no matches. No generated firmware, recordings, CAD work or reports were staged.
