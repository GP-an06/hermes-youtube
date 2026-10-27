# 🎥 Hermes YouTube Multi-Channel Plugin

Plugin tích hợp chính thức **YouTube Data API v3** vào Hermes Agent, chuyên dụng cho bài toán **quản lý và đăng tải nội dung tự động lên nhiều kênh YouTube trên cùng một tài khoản Google (email)**.

---

## 🌟 Tính năng nổi bật

1. **Quản lý Multi-Channel trên 1 Email:**
   - Kết nối không giới hạn số lượng kênh YouTube (Personal Channels & Brand Accounts) thuộc cùng 1 email hoặc nhiều email khác nhau.
   - Quản lý kênh qua **Alias** ngắn gọn (ví dụ: `store_us_1`, `tiktok_reup`, `pod_brand`) hoặc `Channel ID`.
   - Lưu trữ token độc lập, mã hóa phân quyền an toàn (`chmod 600`), tự động làm mới access token khi hết hạn.

2. **Upload Resumable Chuẩn YouTube:**
   - Hỗ trợ cả **YouTube Shorts** (dưới 60s, tỷ lệ 9:16) và **Long-form Videos** dung lượng lớn (hàng trăm MB đến vài GB).
   - Cơ chế chia chunk (8MB/chunk) bền bỉ, tự động retry khi mạng chập chờn, không lo gián đoạn.

3. **Tối ưu SEO & Tự Động Hóa:**
   - Đặt Title, Description (links, hashtags), SEO Tags, Category ID.
   - Upload kèm **Custom Thumbnail** (.jpg, .png) trong cùng 1 lần gọi.
   - Tự động gán video vào **Playlist**.
   - Hỗ trợ **Hẹn giờ công khai** (`publish_at` với `privacy_status="private"`).
   - Tự động sinh Title từ tên file nếu Sếp không truyền tiêu đề.

4. **Trả kết quả trực tiếp:**
   - Trả về link video ngắn: `https://youtu.be/{video_id}`
   - Trả về link đầy đủ: `https://www.youtube.com/watch?v={video_id}`
   - Trả về link chỉnh sửa YouTube Studio: `https://studio.youtube.com/video/{video_id}/edit`

---

## 🛠️ Danh sách Tools cung cấp cho Hermes

| Tool | Mô tả |
|---|---|
| `youtube_upload_video` | Upload video lên kênh chỉ định (hoặc kênh mặc định) kèm thumbnail, tags, playlist, mô tả. |
| `youtube_list_channels` | Liệt kê tất cả các kênh YouTube đã kết nối, alias, channel ID, subs, video count. |
| `youtube_get_channel` | Xem thông số chi tiết của 1 kênh cụ thể. |
| `youtube_list_videos` | Liệt kê các video gần đây trên kênh. |
| `youtube_update_video` | Cập nhật lại title, description, tags, privacy hoặc thumbnail của video đã đăng. |
| `youtube_set_default_channel` | Đổi kênh mặc định khi upload không truyền tên kênh. |
| `youtube_status` | Kiểm tra tình trạng kết nối và độ sẵn sàng của plugin. |

---

## 🚀 Hướng dẫn thiết lập ban đầu (3 bước)

### Bước 1: Chuẩn bị trên Google Cloud Console (GCP)
*(Chỉ cần làm 1 lần duy nhất trên project GCP)*

1. Truy cập [Google Cloud Console](https://console.cloud.google.com).
2. Tạo Project mới (ví dụ: `Hermes YouTube Automation`).
3. Bật **YouTube Data API v3**:
   - Vào menu **APIs & Services** > **Library**.
   - Tìm kiếm `YouTube Data API v3` và click **ENABLE**.
4. Cấu hình **OAuth Consent Screen**:
   - Chọn **External** (bắt buộc để hỗ trợ các kênh Brand Account).
   - Điền Tên App (ví dụ: `Hermes Agent`) và email liên hệ.
   - Tại mục **Test users**: Nhấn **+ ADD USERS** và nhập email Google quản lý các kênh YouTube.
5. Tạo **OAuth Client ID**:
   - Vào menu **APIs & Services** > **Credentials** > **+ CREATE CREDENTIALS** > **OAuth client ID**.
   - Application type: Chọn **Web application**.
   - **Authorized redirect URIs**: Thêm `http://127.0.0.1:8089` và `http://localhost:8089`.
   - Lưu lại, bạn sẽ có `Client ID` và `Client Secret`.

---

### Bước 2: Kết nối kênh qua Setup Wizard

Trên terminal của server/máy chạy Hermes, chạy lệnh:

```bash
python3 /root/.hermes/plugins/youtube/setup_oauth.py --add
```

* Wizard sẽ hướng dẫn nhập `Client ID` và `Client Secret` (hoặc tự động nhận diện nếu đã có file `google_client_secret.json`).
* Script sẽ in ra đường link ủy quyền OAuth.
* Sếp mở link trên trình duyệt, đăng nhập email Google của mình.
* **Màn hình Google sẽ liệt kê toàn bộ các Kênh / Brand Account thuộc email đó.**
* **Sếp click chọn Kênh muốn kết nối và bấm "Cho phép".**
* Trình duyệt sẽ chuyển hướng về `http://127.0.0.1:8089` và báo thành công!
* Wizard sẽ hỏi đặt `alias` (tên gợi nhớ, ví dụ: `store1`, `pod_us`, `shorts_channel`).

> **💡 Muốn thêm kênh thứ 2, thứ 3... trên cùng mail đó?**  
> Sếp chỉ cần chạy lại lệnh:
> ```bash
> python3 /root/.hermes/plugins/youtube/setup_oauth.py --add
> ```
> Mở link, chọn Kênh tiếp theo trên màn hình Google. Hệ thống sẽ tự động thêm vào danh sách kênh mà không ảnh hưởng tới kênh trước!

---

### Bước 3: Quản lý danh sách kênh

* **Xem các kênh đã kết nối:**
  ```bash
  python3 /root/.hermes/plugins/youtube/setup_oauth.py --list
  ```
* **Đổi kênh mặc định:**
  ```bash
  python3 /root/.hermes/plugins/youtube/setup_oauth.py --set-default store1
  ```
* **Gỡ kênh:**
  ```bash
  python3 /root/.hermes/plugins/youtube/setup_oauth.py --remove store1
  ```

---

## 💬 Ví dụ mẫu khi ra lệnh cho Hermes Agent trong Chat

1. **Upload video đơn giản (tự sinh title theo tên file, kênh mặc định):**
   > *"Hermes, upload video `/root/videos/promo_mug.mp4` lên YouTube giúp Sếp, để chế độ unlisted nhé."*

2. **Upload video chỉ định kênh cụ thể kèm SEO metadata:**
   > *"Hermes, upload file `/root/videos/funny_cat_shirt.mp4` lên kênh `store1`. Title: 'Custom Cat Mom T-Shirt Review 2026', tags: ['cat shirt', 'pod gift', 'cat lover'], description: 'Check out this awesome tee at: https://mystore.com/cat-shirt. Giảm 20% với mã CATMOM'."*

3. **Upload kèm thumbnail tùy chỉnh và playlist:**
   > *"Hermes, đăng video `/root/videos/vlog.mp4` lên kênh `pod_brand`. Thumbnail ở `/root/images/thumb.jpg`, thêm luôn vào playlist `PLxxxxxx`."*

4. **Kiểm tra kênh và video gần đây:**
   > *"Hermes, liệt kê các kênh YouTube đang kết nối và xem 5 video mới nhất của kênh `store1`."*
