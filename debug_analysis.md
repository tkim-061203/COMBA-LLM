# Root-Cause Analysis — 3 Module Failures (LangGraph Benchmark)

---

## 1. `alu` — R4 vi phạm: Value / Amount bị swap + dùng concat thay vì operator

### Generated code sai (gvd)

```verilog
SLL:  res = {a[31:0], a[31:0]};   // WRONG: concat a với chính nó
SRL:  res = {b[0], a[31:1]};      // WRONG: manual bit-shift bằng concat
SRA:  res = {b[0], a[31], a[31:1]};
SLLV: res = {a[31:0], a[31:0]};   // WRONG: b (value) bị bỏ qua hoàn toàn
SRLV: res = {b[4:0], a[31:5]};    // WRONG: concat thay vì >>
SRAV: res = {b[4:0], a[31], a[31:5]};
LUI:  res = {b[15:0], 16'b0};     // WRONG: dùng b thay vì a
```

### Root cause (3 lớp)

| # | Lỗi | Giải thích |
|---|---|---|
| 1 | **Operand swap** | MIPS convention: `b` = data value, `a[4:0]` = shift amount. Model swap ngược |
| 2 | **Không dùng operator** | Tự implement bằng concatenation thay vì `<<`, `>>`, `>>>` → sai logic |
| 3 | **LUI sai operand** | Spec: shift `a[15:0]` lên 16 bit; model dùng `b[15:0]` |

### Cross-check từ trace

```
simtime 1: aluc=0x4 (SLLV), a=0x12f17de1, b=0x0970724c
  OUTPUT: r=0x12f17de1  ← trả lại a nguyên (không shift gì cả)
  EXPECT: r=0x12e0e498  ← b << (a[4:0]=1) = 0x0970724c << 1 ✓

simtime 83: aluc=0xf (LUI), a=0x2311223c, b=0x72df3b42
  OUTPUT: r=0x3b420000  ← b[15:0]<<16
  EXPECT: r=0x223c0000  ← a[15:0]<<16 ✓

simtime 21: aluc=0x6 (SRLV), a=0x30139e95, b=0x2135e56a
  OUTPUT: r=0x51809cf4  ← concat, không phải shift
  EXPECT: r=0x00000109  ← b >> a[4:0] = 0x2135e56a >> 21 = 0x109 ✓
```

### Fix đề xuất cho R4

```
### R4: SHIFT & ALU (MIPS convention)
- For MIPS shift instructions (SLL/SRL/SRA/SLLV/SRLV/SRAV):
  → VALUE (data to be shifted) = `b`
  → AMOUNT (shift count) = `a[4:0]`
  → ALWAYS use <<, >>, >>> operators. NEVER implement shift via concatenation.
  → SLL / SLLV : res = b << a[4:0]
  → SRL / SRLV : res = b >> a[4:0]
  → SRA / SRAV : res = $signed(b) >>> a[4:0]
- For LUI: the SOURCE operand is `a` (not `b`).
  → res = {a[15:0], 16'b0}
- Arithmetic right shift: $signed(value) >>> amount
```

---

## 2. `pe` (MAC) — Converter thay đổi tên module → benchmark tb.cpp not found

### Vấn đề

```
final_status: fail_ts
sc_trial: 5, ts_trial: 5
edtm: TB:Make failed 5/5 lần
tb_log: make: *** No rule to make target 'tb.cpp'
```

### Root cause

Benchmark lookup `tb.cpp` theo **module name gốc** `pe`. Converter sinh XML:
```xml
<module id="mac">   ← sai, phải là "pe"
```
→ Generator tạo `module mac(...)` → `comba_mac_xxx/` không có `tb.cpp` → Make failed.

**Logic code thực ra đúng:**
```verilog
module mac(input clk, input rst, input [31:0] a, input [31:0] b, output [31:0] c);
    reg [31:0] acc;
    always @(posedge clk or posedge rst) begin
        if (rst) acc <= 32'b0;
        else acc <= acc + a * b;
    end
    assign c = acc;
endmodule
```
Module này đúng logic MAC (Multiply-Accumulate). Chỉ sai **tên**.

### Cơ chế lỗi

Converter thấy "Multiplying Accumulator" → tự đặt tên semantic `mac` thay vì giữ tên gốc `pe`.

### Fix đề xuất — thêm vào `CONVERTER_SYSTEM_PROMPT`

```
## CRITICAL: Module Name Preservation
- The `<module id>` MUST EXACTLY match the module name stated in the spec.
  Do NOT rename, abbreviate, or infer a "better" name.
  - "pe" stays "pe"  (not "mac", not "multiplier")
  - "div_16bit" stays "div_16bit"  (not "divider")
  - "traffic_light" stays "traffic_light"
```

---

## 3. `traffic_light` — R7 thiếu cụ thể: `pass_request` unused + counter timing off

### Vấn đề kép

**Lỗi A — pass_request unused:**
```
sc_log: %Warning-UNUSED: Signal is not used: 'pass_request'
```
Spec: *"When pedestrian button is pressed, if remaining green time > 10 → shorten to 10."*
Generated code: **không có dòng nào xử lý `pass_request`**.

**Lỗi B — counter off-by-one:**
```
simtime 13 (s1_red, pass_request=0)
  OUTPUT: clock=0x8 (8)
  EXPECT: clock=0xa (10)   ← lệch 2

simtime 33 (s3_green)
  OUTPUT: clock=0x38 (56)
  EXPECT: clock=0x3c (60)  ← lệch 4
```

### Root cause

**Vấn đề A**: R7 hiện chỉ nói *"every declared port must affect logic"* — quá chung chung. Model bỏ qua vì nó không có pattern cụ thể để implement `pass_request` trong context FSM-counter.

**Vấn đề B**: XML converter mô tả counter transition sai:
```xml
if green is deactive and p_green is active, cnt is 60
```
→ Dùng **output signal** `green` (1-cycle delayed) để detect state entry,
thay vì `state == s3_green` (combinational).
→ Generator implement đúng XML nhưng XML có timing bug → counter load sai 1-2 cycle.

### Generated code phân tích

```verilog
// pass_request KHÔNG xuất hiện ở đây
s3_green: begin
    if (cnt == 3) begin state <= s2_yellow; cnt <= 5; end
    else begin state <= s3_green; cnt <= cnt - 1; end
end
// Đúng phải thêm:
// if (pass_request && cnt > 10) cnt <= 10;
```

### Fix đề xuất cho R7

```
### R7: TIMER / COUNTER FSM
- Match counter range and transition boundaries to the spec exactly.
- Every input port MUST influence logic — implement its effect explicitly.
- For interrupt/pedestrian-style inputs that modify a counter mid-state:
  → Check the condition INSIDE the FSM state block using the state register.
  → Use STATE variable (not output signal) to guard the condition.
  → Priority: interrupt check BEFORE normal decrement.
  → Example for pass_request shortening green time:
       if (state == s3_green && pass_request && cnt > 10)
           cnt <= 10;
       else if (cnt == threshold)
           ...transition...
       else
           cnt <= cnt - 1;
- Counter reload: assign new cnt value in the SAME cycle as state transition.
  Use `state` to detect entry → do NOT rely on output light signals (they are delayed).
```

---

## Tổng kết & Priority

| Module | Loại lỗi | Root cause tóm tắt | Ảnh hưởng |
|---|---|---|---|
| `alu` | Semantic (R4) | Swap b↔a trong shift; concat thay vì operator; LUI dùng sai operand | High — fail hoàn toàn mọi shift/LUI test case |
| `pe` | Infrastructure | Converter đổi tên `pe`→`mac` → tb.cpp not found | Critical — 5/5 trial fail hoàn toàn dù code đúng |
| `traffic_light` | Logic (R7) | `pass_request` không được implement; counter timing off do dùng output thay vì state | High — fail cả 5 ts_trial |

**Ưu tiên fix:**
1. `pe` — thêm 1 rule vào Converter, fix ngay 100%.
2. `alu` — làm rõ R4 với MIPS convention + cấm concat cho shift.
3. `traffic_light` — làm rõ R7 với pattern interrupt-inside-FSM + timing rule cho counter load.
