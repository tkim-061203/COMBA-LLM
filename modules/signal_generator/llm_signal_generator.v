module signal_generator(
    input clk,
    input rst_n,
    output reg [4:0] wave
);
    reg state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 0;
            wave <= 0;
        end else begin
            case (state)
                0: begin // Incrementing state
                    if (wave != 31) begin
                        wave <= wave + 1;
                    end else begin
                        state <= 1;
                    end
                end
                1: begin // Decrementing state
                    if (wave != 0) begin
                        wave <= wave - 1;
                    end else begin
                        state <= 0;
                    end
                end
            endcase
        end
    end
endmodule
