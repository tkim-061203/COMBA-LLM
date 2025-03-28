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

    reg [7:0] dividend_reg;
    reg [7:0] divisor_reg;
    reg [8:0] NEG_DIVISOR;
    reg [9:0] SR;
    reg [3:0] cnt;
    reg start_cnt;

    wire [8:0] divisor_extend;
    wire [9:0] all_sub_result;
    wire [8:0] sub_result;
    wire [9:0] sub_remainer_reg_divisor;
    wire [7:0] REMAINER;
    wire [7:0] QUOTIENT;
    wire CO;
    wire [8:0] mux_result;
    wire [6:0] quotient_shift;
    wire [7:0] dividend_abs;
    wire [7:0] final_remainer;
    wire [7:0] final_quotient;
    wire is_final_quotient_sign;

    assign divisor_extend = (sign && divisor[7]) ? {1'b1, divisor} : {1'b0, divisor};
    assign all_sub_result = REMAINER + NEG_DIVISOR;
    assign sub_result = all_sub_result[8:0];
    assign REMAINER = SR[9:2];
    assign QUOTIENT = SR[1:0];
    assign CO = all_sub_result[9];
    assign mux_result = CO ? sub_result : REMAINER;
    assign quotient_shift = SR[8:2];
    assign dividend_abs = (sign && dividend[7]) ? ~dividend + 1'b1 : dividend;
    assign final_remainer = (sign && dividend[7]) ? ~REMAINER + 1'b1 : REMAINER;
    assign is_final_quotient_sign = sign && (dividend[7] ^ divisor[7]);
    assign final_quotient = is_final_quotient_sign ? ~QUOTIENT + 1'b1 : QUOTIENT;
    assign result = {final_remainer, final_quotient};

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            dividend_reg <= 8'b0;
            divisor_reg <= 8'b0;
            SR <= 10'b0;
            NEG_DIVISOR <= 9'b0;
            cnt <= 4'b0;
            start_cnt <= 1'b0;
            res_valid <= 1'b0;
        end else begin
            if (opn_valid && !res_valid && !start_cnt) begin
                dividend_reg <= dividend;
                divisor_reg <= divisor;
                SR <= {dividend_abs, 1'b0};
                NEG_DIVISOR <= (sign && divisor[7]) ? divisor_extend : ~divisor_extend + 1'b1;
                cnt <= 4'b1;
                start_cnt <= 1'b1;
            end
            if (start_cnt) begin
                if (cnt[3]) begin
                    cnt <= 4'b0;
                    start_cnt <= 1'b0;
                    SR[9:2] <= mux_result;
                    SR[0] <= CO;
                    res_valid <= 1'b1;
                end else begin
                    cnt <= cnt + 1'b1;
                    SR <= {mux_result[7:0], quotient_shift, CO, 1'b0};
                end
            end
            if (res_valid && res_ready) begin
                res_valid <= 1'b0;
            end
        end
    end
endmodule
