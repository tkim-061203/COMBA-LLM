module cla_4bit(
    input  [3:0] a,
    input  [3:0] b,
    input  cin,
    output [3:0] sum,
    output cout,
    output g_group,
    output p_group
);
    wire [3:0] p;
    wire [3:0] g;
    wire [4:0] c;

    assign p = a ^ b;
    assign g = a & b;

    assign c[0] = cin;
    assign c[1] = g[0] ^ (p[0] & c[0]);
    assign c[2] = g[1] ^ (p[1] & c[1]);
    assign c[3] = g[2] ^ (p[2] & c[2]);
    assign c[4] = g[3] ^ (p[3] & c[3]);

    assign sum = p ^ c[3:0];
    assign cout = c[4];

    assign p_group = &p;
    assign g_group = g[3] | (g[2] & p[3]) | (g[1] & p[3] & p[2]) | (g[0] & p[3] & p[2] & p[1]);
endmodule


module cla_16bit(
    input  [15:0] a,
    input  [15:0] b,
    input  cin,
    output [15:0] sum,
    output cout
);
    wire [3:0] p;
    wire [3:0] g;
    wire [4:0] c;

    cla_4bit cla0(
        .a(a[3:0]),
        .b(b[3:0]),
        .cin(cin),
        .sum(sum[3:0]),
        .cout(c[1]),
        .g_group(g[0]),
        .p_group(p[0])
    );
    cla_4bit cla1(
        .a(a[7:4]),
        .b(b[7:4]),
        .cin(c[0]),
        .sum(sum[7:4]),
        .cout(c[2]),
        .g_group(g[1]),
        .p_group(p[1])
    );
    cla_4bit cla2(
        .a(a[11:8]),
        .b(b[11:8]),
        .cin(c[2]),
        .sum(sum[11:8]),
        .cout(c[3]),
        .g_group(g[2]),
        .p_group(p[2])
    );
    cla_4bit cla3(
        .a(a[15:12]),
        .b(b[15:12]),
        .cin(c[3]),
        .sum(sum[15:12]),
        .cout(cout),
        .g_group(g[3]),
        .p_group(p[3])
    );

    assign c[0] = cin;
    assign c[1] = g[0] ^ (p[0] & c[0]);
    assign c[2] = g[1] ^ (p[1] & c[1]);
    assign c[3] = g[2] ^ (p[2] & c[2]);

endmodule


module adder_32bit(
    input  [31:0] A,
    input  [31:0] B,
    output [31:0] S,
    output C32
);
    wire [15:0] sum0, sum1;
    wire cout0, cout1;

    cla_16bit cla_low(
        .a(A[15:0]),
        .b(B[15:0]),
        .cin(1'b0),
        .sum(sum0),
        .cout(cout0)
    );

    cla_16bit cla_high(
        .a(A[31:16]),
        .b(B[31:16]),
        .cin(cout0),
        .sum(sum1),
        .cout(C32)
    );

    assign S = {sum1, sum0};
endmodule
