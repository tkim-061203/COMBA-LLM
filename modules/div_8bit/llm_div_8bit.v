module div_8bit(
    input clk,
    input rst,
    input sign,
    input [7:0] dividend,
    input [7:0] divisor,
    input opn_valid,
    input res_ready,
    output reg res_valid,
    output [15:0] result
);

    reg [7:0] dividend_reg, divisor_reg;
    reg [15:0] SR;
    reg [3:0] cnt;
    reg start_cnt;
    wire [8:0] divisor_extend;
    reg [8:0] NEG_DIVISOR;
    reg [9:0] all_sub_result;
    wire [8:0] sub_result;
    wire [8:0] REMAINER;
    wire [8:0] QUOTIENT;
    wire CO;
    wire [8:0] mux_result;
    wire [6:0] quotient_shift;
    wire [8:0] dividend_abs;
    wire [8:0] final_remainer;
    wire [8:0] final_quotient;
    wire is_final_quotient_sign;

    assign divisor_extend = {sign && divisor[7], divisor};
    assign sub_result = all_sub_result[8:0];
    assign REMAINER = SR[15:8];
    assign QUOTIENT = SR[7:0];
    assign CO = all_sub_result[9];
    assign mux_result = CO ? sub_result : REMAINER;
    assign quotient_shift = SR[7:1];
    assign dividend_abs = (sign && dividend[7]) ? ~dividend + 1 : dividend;
    assign final_remainer = (sign && dividend[7]) ? ~REMAINER + 1 : REMAINER;
    assign final_quotient = (is_final_quotient_sign) ? ~QUOTIENT + 1 : QUOTIENT;
    assign is_final_quotient_sign = sign && (dividend[7] ^ divisor[7]);
    assign result = {final_remainer, final_quotient};

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            dividend_reg <= 0;
            divisor_reg <= 0;
            SR <= 0;
            cnt <= 0;
            start_cnt <= 0;
            res_valid <= 0;
        end else if (opn_valid && !start_cnt) begin
            dividend_reg <= dividend;
            divisor_reg <= divisor;
            SR <= {dividend_abs, 1'b0};
            NEG_DIVISOR <= (sign && divisor[7]) ? divisor_extend : ~divisor_extend + 1;
            cnt <= 1;
            start_cnt <= 1;
        end else if (start_cnt) begin
            if (cnt == 8) begin
                cnt <= 0;
                start_cnt <= 0;
            end else begin
                cnt <= cnt + 1;
                all_sub_result <= NEG_DIVISOR + REMAINER; // Drive all_sub_result
                SR <= {mux_result, quotient_shift, CO, 1'b0};
            end
        end
    end

    always @(*) begin
        if (rst) begin
            res_valid = 0;
        end else if (cnt == 8) begin
            res_valid = 1;
        end else if (res_valid && res_ready) begin
            res_valid = 0;
        end else begin
            res_valid = res_valid;
        end
    end

endmodule
