module alu(
    input  [31:0] a,
    input  [31:0] b,
    input  [5:0] aluc,
    output [31:0] r,
    output zero,
    output carry,
    output negative,
    output overflow,
    output flag
);
    parameter ADD  = 6'b100000;
    parameter ADDU = 6'b100001;
    parameter SUB  = 6'b100010;
    parameter SUBU = 6'b100011;
    parameter AND  = 6'b100100;
    parameter OR   = 6'b100101;
    parameter XOR  = 6'b100110;
    parameter NOR  = 6'b100111;
    parameter SLT  = 6'b101010;
    parameter SLTU = 6'b101011;
    parameter SLL  = 6'b000000;
    parameter SRL  = 6'b000010;
    parameter SRA  = 6'b000011;
    parameter SLLV = 6'b000100;
    parameter SRLV = 6'b000110;
    parameter SRAV = 6'b000111;
    parameter LUI  = 6'b001111;

    wire [32:0] res;
    assign res = (aluc == SLL) ? {1'b0, b << a} :
                 (aluc == SRL) ? {1'b0, b >> a} :
                 (aluc == SRA) ? {b[31], b >> a} :
                 (aluc == SLLV) ? {1'b0, b << a[4:0]} :
                 (aluc == SRLV) ? {1'b0, b >> a[4:0]} :
                 (aluc == SRAV) ? {b[31], b >> a[4:0]} :
                 (aluc == ADD)  ? a + b :
                 (aluc == ADDU) ? a + b :
                 (aluc == SUB)  ? a - b :
                 (aluc == SUBU) ? a - b :
                 (aluc == AND)  ? {1'b0, a} & {1'b0, b} :
                 (aluc == OR)   ? {1'b0, a} | {1'b0, b} :
                 (aluc == XOR)  ? {1'b0, a} ^ {1'b0, b} :
                 (aluc == NOR)  ? ~({1'b0, a} | {1'b0, b}) :
                 (aluc == SLT)  ? {32'b0, (a < b)} :
                 (aluc == SLTU) ? {32'b0, ($unsigned(a) < $unsigned(b))} :
                 (aluc == LUI)  ? {a[15:0], 16'b0} :
                 33'b0;

    assign r = res[31:0];
    assign zero = (r == 32'b0);
    assign carry = (aluc == ADD || aluc == ADDU || aluc == SUB || aluc == SUBU) ? res[32] : 1'b0;
    assign overflow = (aluc == ADD) ? ((~a[31] & ~b[31] & r[31]) | (a[31] & b[31] & ~r[31])) :
                       (aluc == SUB) ? ((a[31] & ~b[31] & ~r[31]) | (~a[31] & ~b[31] & r[31])) :
                       1'b0;
    assign negative = r[31];
    assign flag = (aluc == SLT) ? (a < b) :
                  (aluc == SLTU) ? ($unsigned(a) < $unsigned(b)) :
                  1'b0;
endmodule
