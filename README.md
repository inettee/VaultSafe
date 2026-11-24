# VaultSafe

VaultSafe là ứng dụng Windows để lưu mật khẩu trong kho mã hóa trên máy. Bạn có thể tìm tài khoản, sao chép mật khẩu khi cần, kiểm tra đường link đăng nhập và lưu từ Chrome vào hồ sơ đang mở.

## Bắt đầu trên Windows

1. Giải nén toàn bộ gói `VaultSafe-Windows-x64.zip` vào một thư mục riêng.
2. Mở `VaultSafe.exe` trong thư mục đã giải nén. Giữ thư mục `_internal` và các tệp đi kèm cùng vị trí với ứng dụng.
3. Nếu dùng lần đầu, bấm **Tạo hồ sơ**. Đặt tên hồ sơ, nhập mật khẩu chính từ 12 đến 128 ký tự và nhập lại để xác nhận. Khi ứng dụng hỏi nơi lưu tệp `.vaultkey`, hãy chọn một nơi riêng tư.
4. Chọn hồ sơ, nhập mật khẩu chính và bấm **Mở khóa**. Nếu đã dùng VaultSafe trên máy này, bạn có thể mở hồ sơ hiện có.

Dữ liệu mặc định nằm trong `%LOCALAPPDATA%\VaultSafe`. Gói Windows là bản chạy sẵn. Mục **Code → Download ZIP** trên GitHub tải mã nguồn.

## Thêm và dùng tài khoản

- Để thêm tài khoản, bấm **+** cạnh ô tìm kiếm, chọn **Đăng nhập**, điền tên dịch vụ, tên đăng nhập và mật khẩu rồi bấm **Lưu**. Bạn có thể thêm địa chỉ trang web, thư mục và ghi chú.
- Để dùng tài khoản đã lưu, gõ tên dịch vụ hoặc tên đăng nhập vào ô tìm kiếm rồi chọn kết quả. Bấm **Sao chép** cạnh mật khẩu để dán vào trang đăng nhập, hoặc bấm **Hiện** để xem.
- Để chuyển nhiều mục từ Chrome hoặc Bitwarden, mở **Quản lý kho → Nhập tài khoản CSV**, chọn tệp và kiểm tra hồ sơ đích cùng bản xem trước rồi bấm **Nhập vào kho**. Tệp CSV có thể chứa mật khẩu dạng văn bản, nên hãy giữ tệp ở nơi riêng tư.

Bạn có thể đánh dấu mục yêu thích, sắp xếp theo thư mục, khôi phục mục trong **Thùng rác** và dùng **Đổi hồ sơ** để chuyển kho. Khi rời máy, bấm **Khóa kho** ở cuối menu. Trong **Quản lý kho → Bảo vệ phiên**, bạn có thể chỉnh thời gian tự khóa và thời gian dọn mật khẩu đã sao chép.

## Dùng tiện ích Chrome

### Kết nối lần đầu

Cần Chrome 127 trở lên và gói VaultSafe cho Windows.

1. Mở `Thiet-lap-Chrome.exe` trong gói Windows và bấm **Kết nối và mở Chrome**.
2. Ở trang tiện ích, bật **Chế độ dành cho nhà phát triển** (Developer mode) và bấm **Tải tiện ích đã giải nén** (Load unpacked). Dán đường dẫn đã được chép sẵn và chọn thư mục `chrome_extension`.
3. Mở `VaultSafe.exe`, mở khóa hồ sơ bạn muốn dùng, rồi chọn **VaultSafe for Chrome** trong menu tiện ích của Chrome. Popup sẽ hiển thị trạng thái kết nối và tên hồ sơ đang mở.

Khi đổi vị trí thư mục ứng dụng, mở lại công cụ thiết lập từ thư mục mới. Nếu Chrome đang trỏ vào thư mục cũ, gỡ bản đó rồi tải `chrome_extension` từ gói mới. Nếu đã tải đúng thư mục và vừa cập nhật các tệp, bấm **Tải lại** trong trang tiện ích. Để gỡ kết nối, chọn **Ngắt kết nối** trong công cụ thiết lập.

### Lưu thông tin đăng nhập

Trên trang HTTPS có biểu mẫu tương thích, VaultSafe có thể hỏi **Lưu thông tin vừa nhập?** khi bạn gửi biểu mẫu. Hãy kiểm tra địa chỉ trang và hồ sơ đích, rồi bấm **Lưu** khi bạn biết thông tin đúng. Popup báo **Đã lưu** sau khi kho ghi thành công. Nếu mục đã có và mật khẩu khác, hãy kiểm tra lại trước khi bấm **Cập nhật**.

Với trang chuyển hướng nhanh, điền thông tin trên website và mở tiện ích **trước khi bấm Đăng nhập**. Bấm **Lưu vào VaultSafe**, kiểm tra website cùng hồ sơ đích rồi xác nhận **Lưu**. Nếu biểu mẫu đã biến mất hoặc VaultSafe chưa nhận diện được, chọn **Nhập thủ công** trong popup. Tiện ích chỉ đọc mật khẩu từ biểu mẫu khi bạn xác nhận lưu hoặc cập nhật.

Khả năng nhận diện tùy trang. Form trong iframe, đăng nhập nhiều bước, OAuth, OTP và passkey nằm ngoài luồng hỏi lưu chung. Nếu popup báo thiếu quyền, kiểm tra **Quyền truy cập trang web** của tiện ích trên tab đang dùng.

## Kiểm tra bảo mật

- Trong **Công cụ bảo mật → Kiểm tra an toàn**, xem các mục có mật khẩu yếu hoặc dùng lại. Bấm **Mở mục** để xem tài khoản cần xử lý.
- Mở **Trình tạo mật khẩu** để chọn độ dài và nhóm ký tự. Khi thêm hoặc sửa tài khoản, bạn cũng có thể tạo mật khẩu ngay trong biểu mẫu.
- Trong **Công cụ bảo mật → Kiểm tra link đăng nhập**, dán URL và bấm **Kiểm tra**. Đọc tên miền đăng ký và từng lý do cảnh báo trước khi nhập mật khẩu. Công cụ giúp bạn nhận ra dấu hiệu đáng ngờ dựa trên thông tin kiểm tra được.

## Sao lưu và khôi phục

### Tệp `.vaultsafe` lưu bản sao dữ liệu

Mở **Quản lý kho → Sao lưu và khôi phục**, đặt mật khẩu cho bản sao, nhập lại rồi bấm **Tạo tệp sao lưu**. Cất bản sao cùng thông tin cần thiết để tìm lại mật khẩu bản sao khi phục hồi.

Để khôi phục, bấm **Chọn tệp**, mở tệp `.vaultsafe`, nhập mật khẩu bản sao và bấm **Xem trước**. Kiểm tra tên và số mục, đặt tên cùng mật khẩu chính cho hồ sơ mới, rồi bấm **Khôi phục hồ sơ**.

### Tệp `.vaultkey` đặt lại mật khẩu chính của VaultSafe

Ở màn hình **Mở khóa kho**, chọn đúng hồ sơ rồi bấm **Quên mật khẩu? → Chọn tệp khóa**. Khi VaultSafe xác thực tệp `.vaultkey`, đặt mật khẩu chính mới và dùng mật khẩu đó để mở lại hồ sơ. Ai giữ cả kho và tệp khóa có thể đặt lại mật khẩu chính, nên hãy cất tệp khóa riêng khỏi kho.

Nếu hồ sơ chưa có tệp khóa và bạn vẫn mở được kho, vào **Quản lý kho → Bảo vệ phiên → Tạo tệp khóa mới**. Khi tạo tệp mới, các bản sao của tệp khóa cũ sẽ hết hiệu lực. Nếu còn bản sao `.vaultsafe` và mật khẩu bản sao, bạn có thể khôi phục dữ liệu sang hồ sơ mới.

## Chạy từ mã nguồn

Cần Python 3.11 có Tkinter trên Windows. Mở PowerShell tại thư mục repo.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Để thử trên một kho riêng, đặt biến môi trường `VAULTSAFE_DATA_DIR` trỏ vào một thư mục thử trước khi chạy. Tải thư mục `chrome_extension` trong repo để kiểm tra phiên bản tiện ích đang phát triển. Các script trong `native_host` dùng để đăng ký Native Messaging khi làm việc từ mã nguồn.

Để đóng gói bản Windows, cài PyInstaller trong môi trường ảo rồi chạy chương trình tạo gói. Tệp kết quả là `dist/VaultSafe-Windows-x64.zip`.

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe packaging/windows/build.py
```

Chạy bộ kiểm thử kết nối lại từ popup bằng Node.js.

```powershell
node --test tests/test_chrome_form_reconnect.cjs
```

## Cấu trúc mã nguồn

- `main.py` mở ứng dụng Windows. `vaultsafe/` chứa giao diện, kho mã hóa và các công cụ bảo mật.
- `chrome_extension/` chứa tiện ích Chrome. `native_host/` và `setup_chrome.py` phụ trách kết nối Chrome với ứng dụng.
- `tests/` chứa kiểm thử. `packaging/windows/` tạo gói Windows vào `dist/`.
