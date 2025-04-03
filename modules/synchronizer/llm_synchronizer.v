module synchronizer(
    input wire clk_a,
    input wire clk_b,
    input wire arstn,
    input wire brstn,
    input wire [3:0] data_in,
    input wire data_en,
    output reg [3:0] dataout
);

    // Data register to store input data
    reg [3:0] data_reg;
    // Enable data register to store input enable signal
    reg en_data_reg;
    // Enable control registers
    reg en_clap_one;
    reg en_clap_two;

    // Update data_reg on clk_a or reset arstn
    always @(posedge clk_a or negedge arstn) begin
        if (!arstn) begin
            data_reg <= 4'b0000;
        end else begin
            data_reg <= data_in;
        end
    end

    // Update en_data_reg on clk_a or reset arstn
    always @(posedge clk_a or negedge arstn) begin
        if (!arstn) begin
            en_data_reg <= 1'b0;
        end else begin
            en_data_reg <= data_en;
        end
    end

    // Update enable control registers on clk_b or reset brstn
    always @(posedge clk_b or negedge brstn) begin
        if (!brstn) begin
            en_clap_one <= 1'b0;
            en_clap_two <= 1'b0;
        end else begin
            en_clap_one <= en_data_reg;
            en_clap_two <= en_clap_one;
        end
    end

    // Output assignment on clk_b or reset brstn
    always @(posedge clk_b or negedge brstn) begin
        if (!brstn) begin
            dataout <= 4'b0000;
        end else begin
            if (en_clap_two) begin
                dataout <= data_reg;
            end
        end
    end

endmodule
