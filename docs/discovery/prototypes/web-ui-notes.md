# Prototype web-ui: trang chat mới

Ghi chú discovery của nhánh `feat/web-ui`, không phải nguồn chân lý. Phần nào chốt sẽ vào [web.md](../../reference/web.md) khi code xong.

Prototype là đầu vào cho bước code giao diện: FastAPI phục vụ HTML/CSS/JS tĩnh, thay trang Streamlit `src/app.py`.

**Dữ liệu:**
- **Lấy từ corpus** (`data/enriched/chunks.jsonl`, `data/processed/_index.json`, bản crawl 2026-11-12): tên, số hiệu, link, ngày hiệu lực và trích đoạn của văn bản.
- **Giả lập:** câu hỏi, câu trả lời, lịch sử, thời gian trả lời và mã bị gắn cờ `7`. Câu trả lời viết theo các đoạn văn bản thật nhưng không phải output của model.

## Mục lục

| # | Mục |
|---|---|
| 1 | [Cách xem](#1-cách-xem) |
| 2 | [Design system](#2-design-system) |
| 3 | [Các màn](#3-các-màn) |
| 4 | [Đầu vào cho bước code](#4-đầu-vào-cho-bước-code) |
| 5 | [Câu hỏi](#5-câu-hỏi) |

## 1. Cách xem

- **Mở file:** mở [`web-ui.html`](web-ui.html) bằng trình duyệt. File tự chứa CSS và JS, chỉ nạp font từ Google Fonts.
- **Thanh đen dưới cùng** là của prototype, không phải của app:
  - chọn màn S1–S10, hoặc dùng phím ← →;
  - chọn cỡ khung **Desktop / Tablet 1024 / Mobile 390**;
  - bật tắt ghi chú bằng nút hoặc phím N. Khung viền đứt vàng là ghi chú cho người review.
- **Tương tác chạy được:**
  - bấm chip trích dẫn, dòng nguồn hoặc tab để đổi nguồn trong panel;
  - đóng panel bằng nút ×, phím Esc hoặc bấm nền;
  - gửi câu hỏi (Enter) sẽ chạy S4 rồi sang S5;
  - "Thử lại" ở S7 và S2;
  - sao chép, 👍/👎, xóa hội thoại, lọc danh sách văn bản;
  - mở thanh bên bằng nút ☰ ở khung mobile.
- **Responsive** viết bằng container query trên khung app, nên nút đổi cỡ mô phỏng đúng breakpoint. Khi code thật, khung app chính là viewport.

## 2. Design system

Hướng **"Văn bản pháp lý"** (Trust & Authority, Swiss minimal), duyệt ngày 2026-11-18. Gợi ý ban đầu từ skill ui-ux-pro-max; font đã đổi vì Lato thiếu dấu tiếng Việt.

Token nằm trong khối `:root` đầu file HTML. Stylesheet của sản phẩm bắt đầu từ khối đó.

| Nhóm | Giá trị |
|---|---|
| Màu thương hiệu | `--primary` `#1E3A8A` (nút, link, focus); `--accent` `#B45309` (chỉ dùng cho chip trích dẫn và dấu nhấn) |
| Màu nền | `--bg` `#F8FAFC`; `--surface` `#FFFFFF`; `--surface-2` `#F1F5F9` |
| Màu chữ | `--ink` `#0F172A` (17,9:1); `--muted` `#475569` (7,6:1); `--subtle` `#64748B` (4,8:1, chỉ cho chú thích) |
| Màu trạng thái | warn (vàng) cho trích dẫn bị gắn cờ và "đã sửa đổi"; bad (đỏ) cho lỗi. Luôn kèm icon và chữ, không dựa riêng vào màu |
| Font | **Source Serif 4**: thân câu trả lời, tiêu đề văn bản, trích đoạn. **Be Vietnam Pro**: giao diện. **JetBrains Mono**: số trích dẫn. Cả ba có bộ chữ tiếng Việt |
| Cỡ chữ | 12 / 14 / 16 / 17 (câu trả lời) / 18 / 24 / 32; line-height 1,45 (UI), 1,7 (câu trả lời) |
| Khoảng cách, bo góc, bóng | lưới 4/8; bo góc 6 / 8 / 12; hai mức bóng |
| Chuyển động | 150 / 220 ms; tắt khi `prefers-reduced-motion` |
| Icon | Lucide, SVG sprite, nét 1,75; không dùng emoji |
| Bố cục | thanh bên 280 px · cột đọc tối đa 760 px · panel nguồn 420 px |
| Breakpoint | dưới 1280 px: panel thành ngăn kéo phủ. Dưới 900 px: thanh bên ẩn sau ☰, panel và hộp thoại thành bottom sheet |
| Accessibility | focus ring 2 px; mọi nút icon có `aria-label`; skip link; `aria-live` cho luồng hội thoại; `alertdialog` khi xóa; Esc đóng lớp trên cùng; vùng bấm tối thiểu 32 px (WCAG 2.2 cần 24) |

Điểm nhận diện là **chip trích dẫn màu hổ phách**:
- câu trả lời trình bày như văn bản, không đặt trong bong bóng;
- câu hỏi của người dùng là bong bóng xanh nhạt bên phải.

## 3. Các màn

| Màn | Nội dung | Hành vi |
|---|---|---|
| S1 · Đang nạp chỉ mục | Thẻ giữa trang có vòng quay, tiêu đề "Đang nạp chỉ mục văn bản", một dòng giải thích ("khoảng 30 giây") và thanh tiến trình chạy liên tục | Trang hỏi API trạng thái mỗi 2 s; nạp xong thì tự sang S3. Ô câu hỏi tắt, placeholder "Chưa thể đặt câu hỏi lúc này". Lịch sử vẫn xem được |
| S2 · Lỗi tải chỉ mục | Thẻ đỏ, giữ nguyên văn `LOAD_ERROR`, thêm một dòng cho người vận hành và nút "Thử lại" | "Thử lại" gọi lại API trạng thái và quay về S1. Không hiện stack trace |
| S3 · Hội thoại mới | Màn chào: tiêu đề, một câu về phạm vi, ba điểm (mỗi ý có nguồn · báo khi luật đã bị sửa · hỏi tiếp), ghi chú `NOTICE`. Không có câu hỏi gợi ý. Lịch sử trống thì hiện một ô viền đứt | "Cuộc hội thoại mới" luôn về màn này, không hỏi xác nhận vì hội thoại cũ còn trong lịch sử |
| S4 · Đang trả lời | Câu hỏi hiện ngay; phần trả lời là khung xám, `SPINNER` "Đang tìm và trả lời…" và bộ đếm giây | Vẫn gõ được câu tiếp theo nhưng nút gửi tắt. Hội thoại hiện ngay ở đầu lịch sử. Không chia bước vì server không báo tiến độ |
| S5 · Câu trả lời và nguồn | Câu trả lời dạng serif với chip 1…n. Danh sách nguồn: văn bản, điều, khoản, mô tả, nhãn "Đã sửa đổi", link mở tab mới. Dòng vàng cho trích dẫn bị gắn cờ (chip "?"). `NOTICE` dưới mọi câu trả lời. Hàng nút sao chép / 👍 / 👎, thời gian trả lời, số nguồn | Bấm chip hoặc dòng nguồn để mở panel: loại văn bản, số hiệu, vị trí, ngày ban hành, ngày hiệu lực của chính điều khoản (nhãn "hồi tố, trước ngày ban hành" khi sớm hơn), cảnh báo sửa đổi kèm nút "Xem nguồn [n]", trích đoạn có tô sáng, nút mở văn bản gốc. Nguồn đầu tiên tự mở trên desktop rộng |
| S6 · Không tìm thấy | Nguyên văn `NOT_FOUND` màu nhạt hơn; khung "Thử hỏi lại" gồm ba gợi ý và link tới danh sách văn bản; `NOTICE` | Không có nguồn, không có panel |
| S7 · Lỗi khi trả lời | Khung đỏ có icon, nguyên văn `ERROR`, câu "Câu hỏi chưa được lưu vào hội thoại", nút "Thử lại" và "Sửa câu hỏi" | "Thử lại" gửi lại đúng câu đó. "Sửa câu hỏi" đưa câu hỏi về ô nhập. Hết quota hoặc vượt nhịp cũng hiện thông báo này (Q2) |
| S8 · Hội thoại nhiều lượt | Hai lượt: thuế GTGT, rồi "Còn thuế thu nhập cá nhân thì sao?" | Mỗi câu trả lời có danh sách nguồn riêng, đánh số lại từ 1. Tiêu đề panel ghi "Nguồn · câu trả lời 2". Tiêu đề hội thoại là câu hỏi đầu tiên |
| S9 · Xóa hội thoại | Icon thùng rác ở dòng lịch sử (hiện khi rê chuột hoặc focus, luôn hiện ở dòng đang mở). Hộp xác nhận: "… sẽ bị xóa khỏi trình duyệt này. Không khôi phục được.", nút "Hủy" và "Xóa" (đỏ) | Esc hoặc bấm nền để hủy. Xóa xong hiện toast "Đã xóa hội thoại"; nếu xóa hội thoại đang mở thì về S3 |
| S10 · Danh sách văn bản | Hộp thoại lớn: 30 văn bản chia ba nhóm Luật (7) / Nghị định (11) / Thông tư (12), mỗi dòng có số hiệu, tên, link gốc; ô lọc. Không có cột ngày (lựa chọn 8A trên #30) | Mở từ "Xem danh sách" ở chân thanh bên và từ S6. Lọc theo số hiệu hoặc tên ngay khi gõ |

**Chữ của app:** giữ nguyên các hằng số hiện có của `src.app`: `TITLE`, `PLACEHOLDER`, `NOTICE`, `NEW_CONVERSATION`, `SPINNER`, `ERROR`, `LOAD_ERROR`. Các chữ mới (màn chào, gợi ý hỏi lại, hộp xác nhận, toast) lấy theo prototype.

## 4. Đầu vào cho bước code

Prototype dựng màn từ dữ liệu có cấu trúc (`TURNS` / `SRC` trong script), không từ Markdown `Answer.text`. Bước code cần những phần sau.

**API**

| Endpoint | Trả về |
|---|---|
| `GET /api/status` | `loading` · `ready` · `error` (S1, S2) |
| `POST /api/ask` | Vào: câu hỏi và các câu hỏi trước của hội thoại. Ra: `sentences[{text, citations}]`, `sources[]`, `flagged[]`, `not_found`, `latency_s`. Mỗi phần tử `sources[]` có `document`, `kind`, `article`, `clause`, `desc`, `url`, `issued`, `effective`, `excerpt`, `amended_by` |
| `GET /api/documents` | 30 văn bản cho S10, hoặc một file JSON tĩnh (Q5) |

**Ngoài phạm vi trang** (backend phải bổ sung):
- `Citation` chưa có nội dung đoạn: `passage` hiện chỉ là id (Q1).
- `Answer` chưa có mô tả văn bản, ngày ban hành, ngày hiệu lực, quan hệ sửa đổi ở dạng có cấu trúc. Các dữ liệu này có sẵn trong chunk (`effective_date`, `amended_by`), trong header và trong metadata văn bản (`ngay_ban_hanh`).

**Phía trang**
- Đánh số lại trích dẫn thành 1…n theo thứ tự xuất hiện. Mã bị gắn cờ hiện chip "?" và nêu mã gốc trong dòng cảnh báo.
- Ghi chú `NOTICE` thuộc về trang, không thuộc `Answer.text`, như lựa chọn 2A hiện tại.
- Lịch sử hội thoại lưu trong `localStorage` (Q7).
- Rewriter `concat` chỉ cần các câu hỏi trước, nên API không phải giữ session (Q6).
- Một câu hỏi bị lỗi không được tính vào hội thoại, như `Session.ask` hiện nay.

## 5. Câu hỏi

- **Q1** (S5): panel cần trích đoạn của điều khoản. Thêm nội dung chunk vào `Citation` và vào response của API được không? Nếu không, panel chỉ còn thông tin văn bản và link.
- **Q2** (S7): khi hết quota hoặc vượt nhịp 15 câu/phút, có hiện thông báo riêng không (ví dụ "Đang có nhiều câu hỏi, thử lại sau một phút")? Prototype giữ chung `ERROR`.
- **Q3** (S5): 👍/👎 lưu ở đâu: chỉ trên trình duyệt, hay gửi về server ghi vào file (log JSONL) để bổ sung bộ eval?
- **Q4** (S8): tiêu đề hội thoại lấy câu hỏi đầu tiên (không tốn thêm lần gọi model). Đồng ý không?
- **Q5** (S10): danh sách văn bản lấy qua API, hay xuất một file JSON tĩnh lúc dựng chỉ mục?
- **Q6**: API không giữ trạng thái, trang gửi kèm các câu hỏi trước; nhờ vậy mở lại hội thoại cũ sau khi server khởi động lại vẫn hỏi tiếp được. Hay giữ session phía server theo id?
- **Q7** (S9): lịch sử chỉ nằm trên một trình duyệt, không đồng bộ giữa các máy. Có cần giới hạn số hội thoại (ví dụ 50, xóa cái cũ nhất) không?
- **Q8** (S5, S10): ngày hiệu lực. **Đã chốt** trên #30 (8A, cộng phần đính chính): panel hiện ngày hiệu lực của chính điều khoản được trích và ngày ban hành của văn bản; S10 không có cột ngày. Ngày 01/01/2026 của Nghị định 141/2026 (ban hành 29/04/2026) và của Luật 09/2026/QH16 (ban hành 24/04/2026) là hiệu lực hồi tố do chính văn bản quy định, không phải lỗi dữ liệu.
