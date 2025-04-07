module RAM(
    input wire clk,
    input wire rst_n,
    input wire write_en,
    input wire [2:0] write_addr,
    input wire [5:0] write_data,
    input wire read_en,
    input wire [2:0] read_addr,
    output reg [5:0] read_data
);

    parameter WIDTH = 6;
    parameter DEPTH = 8;

    reg [WIDTH-1:0] internal_RAM [0:DEPTH-1];

    // Write operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Reset all memory locations to 0
            integer i;
            for (i = 0; i < DEPTH; i = i + 1) begin
                internal_RAM[i] <= {WIDTH{1'b0}};
            end
        end else if (write_en) begin
            internal_RAM[write_addr] <= write_data;
        end
    end

    // Read operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_data <= {WIDTH{1'b0}};
        end else if (read_en) begin
            read_data <= internal_RAM[read_addr];
        end else begin
            read_data <= {WIDTH{1'b0}};
        end
    end

endmodule
