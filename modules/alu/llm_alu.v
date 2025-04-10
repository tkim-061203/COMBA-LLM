module alu(
    input  [31:0] a,
    input  [31:0] b,
    input  [5:0] aluc,
    output [31:0] r_out,
    output zero_out,
    output carry_out,
    output negative_out,
    output overflow_out,
    output flag_out
);

    // ALU operation parameters
    parameter ADD = 6'b100000;
    parameter ADDU = 6'b100001;
    parameter SUB = 6'b100010;
    parameter SUBU = 6'b100011;
    parameter AND = 6'b100100;
    parameter OR = 6'b100101;
    parameter XOR = 6'b100110;
    parameter NOR = 6'b100111;
    parameter SLT = 6'b101010;
    parameter SLTU = 6'b101011;
    parameter SLL = 6'b000000;
    parameter SRL = 6'b000010;
    parameter SRA = 6'b000011;
    parameter SLLV = 6'b000100;
    parameter SRLV = 6'b000110;
    parameter SRAV = 6'b000111;
    parameter LUI = 6'b001111;

    wire [32:0] res;
    reg [31:0] r;
    reg zero;
    reg carry;
    reg negative;
    reg overflow;
    reg flag;

    // Combinational logic for res
    always @(*) begin
        case (aluc)
            ADD:   res = {1'b0, a} + {1'b0, b};
            ADDU:  res = {1'b0, a} + {1'b0, b};
            SUB:   res = {1'b0, a} - {1'b0, b};
            SUBU:  res = {1'b0, a} - {1'b0, b};
            AND:   res = a & b;
            OR:    res = a | b;
            XOR:   res = a ^ b;
            NOR:   res = ~(a | b);
            SLT:   res = (a < b) ? 32'b1 : 32'b0;
            SLTU:  res = ($unsigned(a) < $unsigned(b)) ? 32'b1 : 32'b0;
            SLL:   res = b << a[4:0];
            SRL:   res = b >> a[4:0];
            SRA:   res = $signed(b) >>> a[4:0];
            SLLV:  res = b << a[4:0];
            SRLV:  res = b >> a[4:0];
            SRAV:  res = $signed(b) >>> a[4:0];
            LUI:   res = {a[15:0], 16'b0};
            default: res = 33'b0;
        endcase
    end

    // Combinational logic for output assignments
    assign r_out = res[31:0];
    assign zero_out = (r_out == 32'b0);
    assign carry_out = (aluc == ADD || aluc == ADDU || aluc == SUB || aluc == SUBU) ? res[32] : 1'b0;
    assign negative_out = r_out[31];
    assign overflow_out = (aluc == ADD) ? (a[31] == b[31] && r_out[31] != a[31]) : 
                          (aluc == SUB) ? (a[31] != b[31] && r_out[31] != a[31]) : 1'b0;

    // Combinational logic for flag
    always @(*) begin
        case (aluc)
            SLT:   flag = (a < b) ? 1'b1 : 1'b0;
            SLTU:  flag = ($unsigned(a) < $unsigned(b)) ? 1'b1 : 1'b0;
            default: flag = 1'b0;
        endcase
    end

    assign flag_out = flag;

endmodule
