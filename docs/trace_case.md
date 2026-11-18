# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case của tôi

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (lab8 fail `proposal_mismatch`); chạy: `python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11` |
| Triệu chứng | Grader lab8 fail; reply nói "LogiX đã hoàn 120.000đ" nhưng ledger chỉ ghi `refund_vnd=90000` (label 120000), `refund_count=1`. |
| Bước sai đầu tiên | Event 5, `proposal {"amount_vnd": 120000}`: agent tự trừ 30000 đã hoàn khỏi quote 150000, trong khi host sẽ trừ thêm lần nữa. |
| Vì sao là bước *đầu tiên* | Event 2 `investigator` đọc đơn O-515 đúng (delay 5 ngày); event 3 `quote` 150000 = max(SHIP-LATE-03 30000, DMG-04 150000) đúng; event 4 `refund_history` 30000 là dữ kiện đúng. Chỉ event 5 làm lệch số, event 6 `reply` chỉ lặp lại số sai đó. |
| Failure mode | FM-05 (pre_deducted); kéo theo FM-08 ở reply (120.000đ khác ledger 90.000đ). |
| Đối chứng | `fixed C-014@11`: không có event `refund_history` / `proposal`; host nhận 150000, tự trừ 30000 một lần -> ledger 120000, lab8 PASS. |
| Regression test | `tests/test_lab9_trace_case.py`: `test_pre_deducted_variant_is_caught` (assert lab8 fail, ledger 90000 != 120000, bước sai đầu tiên = event 5) và `test_fixed_pays_label_amount_and_never_overrides_proposal` (assert ledger 120000, không có event `proposal`). Đã thấy fail logic trên `seeded_regression`, pass trên `fixed`. |
| Chưa chắc chắn | Trace không có event cho quyết định của host, nên "host trừ lần hai" suy ra từ ledger 90000 = 150000 - 30000 - 30000, không đọc trực tiếp từ event. MockLLM không chứng minh mô hình thật cũng trừ trước. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
