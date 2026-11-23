# VaultSafe

Ứng dụng Windows dùng Python và CustomTkinter để quản lý kho mật khẩu mã hóa theo hồ sơ.

## Chạy ứng dụng

Mở PowerShell trong thư mục này.

```powershell
.\.venv\Scripts\python.exe main.py
```

Nếu cần tạo lại môi trường bằng Python 3.11 có Tkinter, dùng các lệnh sau.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Kho mặc định nằm ở `%LOCALAPPDATA%\VaultSafe\vaultsafe.db`. Biến `VAULTSAFE_DATA_DIR` cho phép dùng thư mục dữ liệu khác.

## Khôi phục khi quên mật khẩu chính

Khi bấm **Tạo hồ sơ**, VaultSafe yêu cầu chọn nơi lưu tệp `.vaultkey`. Tệp chỉ dùng cho hồ sơ vừa tạo. Hãy cất tệp ở nơi riêng, chẳng hạn USB lưu an toàn, và giữ quyền truy cập riêng tư. Ai giữ cả kho và tệp khóa có thể đặt lại mật khẩu chính của hồ sơ.

1. Ở màn hình **Mở khóa kho**, chọn đúng hồ sơ và bấm **Quên mật khẩu?**.
2. Bấm **Chọn tệp khóa** và mở tệp `.vaultkey` đã cất cho hồ sơ đó.
3. Khi VaultSafe xác thực tệp, nhập và xác nhận mật khẩu chính mới. Bấm **Đặt lại mật khẩu**, rồi dùng mật khẩu mới để mở kho. Dữ liệu hồ sơ và tệp khóa vẫn dùng được.

Hồ sơ có từ trước hoặc khôi phục từ tệp sao lưu có thể tạo khóa qua **Quản lý kho → Bảo vệ phiên → Tạo tệp khóa mới** sau khi mở kho và nhập lại mật khẩu chính. Khi tạo tệp khóa mới, các bản sao của tệp cũ mất hiệu lực. Nếu đã quên mật khẩu chính trước khi có tệp khóa, bản sao `.vaultsafe` cùng mật khẩu bản sao có thể dùng để khôi phục vào hồ sơ mới.

## Khôi phục từ bản sao

Trong **Sao lưu và khôi phục**, bấm **Chọn tệp** để mở bản sao `.vaultsafe`. Sau đó nhập mật khẩu đã đặt khi tạo bản sao và bấm **Xem trước**. Kiểm tra tên và số mục, đặt tên cùng mật khẩu chính cho hồ sơ mới, rồi bấm **Khôi phục hồ sơ**.

## Dùng với Chrome

1. Mở `chrome://extensions`, bật **Developer mode**, bấm **Load unpacked** và chọn `chrome_extension`.
2. Sao chép ID tiện ích và chạy lệnh đăng ký Native Messaging trong PowerShell.

   ```powershell
   $extensionId = Read-Host 'ID của VaultSafe for Chrome'
   powershell -NoProfile -ExecutionPolicy Bypass -File .\native_host\register.ps1 -ExtensionId $extensionId
   ```

3. Mở VaultSafe và mở khóa đúng hồ sơ. Nếu đã cài tiện ích, dùng **Reload** trên thẻ VaultSafe trong `chrome://extensions` sau khi cập nhật.

Để gỡ đăng ký Native Messaging, chạy `powershell -NoProfile -ExecutionPolicy Bypass -File .\native_host\unregister.ps1`.

## Tài liệu và bộ thử

README đầy đủ, tài liệu, test, demo và bản đối chiếu Bitwarden được lưu ở thư mục `Final2.0-archive` cạnh project. Nếu cần chạy demo hoặc test như trước, đưa các thư mục tương ứng về lại project.
