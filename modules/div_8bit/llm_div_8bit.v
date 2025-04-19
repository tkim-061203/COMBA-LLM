module div_8bit(
    input clk,
    input rst,
    input sign,
    input [7:0] dividend,
    input [7:0] divisor,
    input opn_valid,
    input res_ready,
    output reg res_valid,
    output reg [15:0] result
);

    reg [7:0] dividend_reg, divisor_reg;
    reg [15:0] SR;
    reg [3:0] cnt;
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
    reg [8:0] final_remainer;
    reg [8:0] final_quotient;
    wire is_final_quotient_sign;
    reg start_cnt;
    reg res_valid_reg;

    assign divisor_extend = (sign && divisor[7]) ? {1'b1, divisor} : {1'b0, divisor};
    assign sub_result = all_sub_result[8:0];
    assign REMAINER = SR[15:8];
    assign QUOTIENT = SR[7:0];
    assign CO = all_sub_result[9];
    assign mux_result = CO ? sub_result : REMAINER;
    assign quotient_shift = SR[7:1];
    assign dividend_abs = (sign && dividend[7]) ? ~dividend + 1'b1 : dividend;
    assign is_final_quotient_sign = sign && (dividend[7] ^ divisor[7]);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            dividend_reg <= 0;
            divisor_reg <= 0;
            SR <= 0;
            cnt <= 0;
            start_cnt <= 0;
            res_valid_reg <= 0;
            all_sub_result <= 0;
        end else begin
            if (opn_valid && !res_valid_reg && !start_cnt) begin
                dividend_reg <= dividend;
                divisor_reg <= divisor;
                SR <= {dividend_abs, 1'b0};
                NEG_DIVISOR <= (sign && divisor[7]) ? divisor_extend : ~divisor_extend + 1'b1;
                cnt <= 1;
                start_cnt <= 1;
            end
            if (start_cnt) begin
                if (cnt == 8) begin
                    cnt <= 0;
                    start_cnt <= 0;
                    res_valid_reg <= 1;
                end else begin
                    cnt <= cnt + 1;
                    all_sub_result <= REMAINER + NEG_DIVISOR;
                    SR <= {mux_result, quotient_shift, CO, 1'b0};
                end
            end
            if (res_ready && res_valid_reg) begin
                res_valid_reg <= 0;
            end
        end
    end

    always @(*) begin
        if (res_valid_reg) begin
            final_quotient = QUOTIENT;
            final_remainer = REMAINER;
        end
    end

    always @(*) begin
        if (sign) begin
            final_quotient = (QUOTIENT[7] ? ~QUOTIENT + 1'b1 : QUOTIENT);
            final_remainer = (REMAINER[7] ? ~REMAINER + 1'b1 : REMAINER);
        end else begin
            final_quotient = QUOTIENT;
            final_remainer = REMAINER;
        end
        result = {final_remainer, final_quotient};
        res_valid = res_valid_reg;
    end

endmodule
