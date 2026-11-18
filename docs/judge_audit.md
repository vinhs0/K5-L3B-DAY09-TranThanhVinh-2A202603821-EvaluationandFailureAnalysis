# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (FAIL là lớp dương: nhiệm vụ của judge là tìm lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Tỉ lệ FAIL quan sát → hiệu chỉnh (Rogan-Gladen) | Quyết định |
|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.8 | Đạt cả 3 (confusion tp=24, fp=4, fn=6, tn=66) | 0.28 → 0.30 | **dùng** |
| helpful | 100 | 0.375 | 1.0 | 0.3 | **Không đạt**: κ 0.375 < 0.6 và recall 0.3 < 0.7 (tp=9, fp=0, fn=21, tn=70); chỉ precision đạt | 0.09 → 0.30 | **loại** |

## Output lệnh (nguyên văn)

`python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
```
n=100 P=0.857 R=0.8 kappa=0.757 {'tp': 24, 'fp': 4, 'fn': 6, 'tn': 66}
fail rate observed 0.28 -> corrected 0.3
  H-008 human=FAIL judge=PASS | Em đã hoàn tiền cho anh rồi nha, anh check giúp em.
  H-017 human=FAIL judge=PASS | Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha.
  H-029 human=FAIL judge=PASS | Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm.
  H-042 human=PASS judge=FAIL | Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ.
  H-051 human=PASS judge=FAIL | Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ.
PASS floors {'kappa': 0.6, 'precision': 0.8, 'recall': 0.7}
```

`python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`
```
n=100 P=1.0 R=0.3 kappa=0.375 {'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}
fail rate observed 0.09 -> corrected 0.3
  HL-015 human=FAIL judge=PASS | Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ.
  HL-016 human=FAIL judge=PASS | Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của
  HL-020 human=FAIL judge=PASS | Dạ, LogiX đã hoàn 90.000đ cho đơn O-303 ạ.
  HL-028 human=FAIL judge=PASS | Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của
  HL-035 human=FAIL judge=PASS | Dạ, Một lần nữa LogiX xin lỗi vì trải nghiệm chưa tốt, mong anh/chị thông cảm và tiếp tục
FAIL floors {'kappa': 0.6, 'precision': 0.8, 'recall': 0.7}
```

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric cụ thể |
|---|---|---|---|---|---|
| 1 | tone H-008: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã; judge coi là thân thiện. Sửa: thêm tiêu chí "xưng hô: dùng 'LogiX/em' kèm 'dạ…ạ', cấm 'nha/nhé/bạn ơi'" và 2 ví dụ few-shot FAIL. |
| 2 | tone H-017: "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Gọi "bạn ơi" với khách lớn tuổi, thêm "nha". Sửa: danh sách từ cấm "bạn ơi, nha, nhé" và bắt buộc gọi "anh/chị". |
| 3 | tone H-029: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh ("không cần nhắn thêm"); judge chỉ thấy "Dạ, vui lòng". Sửa: rubric chấm toàn câu, FAIL nếu có câu mệnh lệnh/phủ định hướng khách dù có mở đầu lịch sự. |
| 4 | tone H-042: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ ý, lịch sự; judge phạt vì "thiếu xin lỗi". Sửa: ghi rõ xin lỗi chỉ bắt buộc khi có sự cố; ngắn gọn không bị trừ. |
| 5 | tone H-051: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | "refund" được CS LogiX cho phép; judge phạt vì tiếng Anh. Sửa: thêm danh sách thuật ngữ được phép (refund, ticket) vào rubric. |
| 6 | helpful HL-015: "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Sai tiền: ledger ghi 40.000đ. Judge không đối chiếu ledger nên bỏ sót. Sửa: không dùng LLM cho số tiền, chấm bằng code (so reply với ledger); judge chỉ chấm phần còn lại. |
| 7 | helpful HL-016: reply dài, xin lỗi lặp, hoàn 55.000đ cho O-404 | PASS | FAIL | Người | Ledger ghi 35.000đ; judge bị đánh lừa bởi lời xin lỗi dài, giọng thấu cảm (verbosity/sycophancy bias). Sửa: rubric "độ dài/xin lỗi không cộng điểm", yêu cầu judge trích số tiền trước khi kết luận. |
| 8 | helpful HL-028: xin lỗi lặp 2 lần, hoàn 50.000đ cho O-677 | PASS | FAIL | Người | Ledger ghi 35.000đ, cùng lỗi như HL-016; lặp câu xin lỗi còn là lỗi văn phong. Sửa: như trên, thêm FAIL cho câu lặp nguyên văn. |

## Kết luận
- **tone_ok: dùng được.** Đạt cả 3 sàn (κ=0.757, P=0.857, R=0.8). Hiệu chỉnh Rogan-Gladen: tỉ lệ FAIL thật ≈ 0.30 (quan sát 0.28). Còn 6 bỏ sót (fn) và 4 báo nhầm (fp); các lỗi đều là biên xưng hô/giọng điệu, sửa được bằng rubric (case 1-5).
- **helpful: loại, KHÔNG được dùng làm gate.** Không đạt 2/3 sàn: recall=0.3 (<0.7) và κ=0.375 (<0.6); precision=1.0 chỉ cho thấy judge hiếm khi báo nhầm, nhưng nó bỏ sót 21/30 lỗi thật (fn=21, tn=70, fp=0). Judge chỉ nói FAIL 9% trong khi tỉ lệ lỗi thật ≈ 30% (sau hiệu chỉnh), nên gate dùng nó sẽ cho qua phần lớn reply sai (đặc biệt reply sai số tiền so với ledger, case 6-8) với cảm giác an toàn giả. Số tiền phải chấm bằng code, không bằng judge.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật. Hiệu chỉnh Rogan-Gladen phụ thuộc ước lượng sens/spec trên n=100 nên còn sai số lấy mẫu.
