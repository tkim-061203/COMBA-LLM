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

    reg [32:0] res; // Changed from wire to reg

    always @(*) begin
        case (aluc)
            ADD, ADDU: res = {1'b0, a} + {1'b0, b};
            SUB, SUBU: res = {1'b0, a} - {1'b0, b};
            AND: res = {1'b0, a} & {1'b0, b}; // Fixed width expansion
            OR:  res = {1'b0, a} | {1'b0, b}; // Fixed width expansion
            XOR: res = {1'b0, a} ^ {1'b0, b}; // Fixed width expansion
            NOR: res = ~({1'b0, a} | {1'b0, b}); // Fixed width expansion
            SLL: res = {1'b0, b} << a; // Fixed width expansion for shift
            SRL: res = {1'b0, b} >> a; // Fixed width expansion for shift
            SRA: res = $signed({1'b0, b}) >>> a; // Fixed width expansion for signed shift
            SLLV: res = {1'b0, b} << a[4:0]; // Fixed width expansion for shift
            SRLV: res = {1'b0, b} >> a[4:0]; // Fixed width expansion for shift
            SRAV: res = $signed({1'b0, b}) >>> a[4:0]; // Fixed width expansion for signed shift
            LUI: res = {a[15:0], 16'b0}; // Fixed width expansion
            SLT: res = ($signed(a) < $signed(b)) ? 1 : 0;
            SLTU: res = (a < b) ? 1 : 0;
            default: res = 33'b0;
        endcase
    end

    assign r = res[31:0];
    assign zero = (r == 32'b0);
    assign carry = (aluc == ADD || aluc == ADDU || aluc == SUB || aluc == SUBU) ? res[32] : 1'b0;
    assign overflow = (aluc == ADD) ? ((~a[31] & ~b[31] & r[31]) | (a[31] & b[31] & ~r[31])) :
                        (aluc == SUB) ? ((a[31] & ~b[31] & ~r[31]) | (~a[31] & ~b[31] & r[31])) : 1'b0;
    assign negative = r[31];
    assign flag = (aluc == SLT) ? ($signed(a) < $signed(b)) :
                  (aluc == SLTU) ? (a < b) : 1'b0;

endmodule
