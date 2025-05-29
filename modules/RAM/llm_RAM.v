module RAM #(parameter WIDTH = 8, parameter DEPTH = 256) (
    input clk,
    input rst_n,
    input write_en,
    input [$clog2(DEPTH)-1:0] write_addr,
    input [WIDTH-1:0] write_data,
    input read_en,
    input [$clog2(DEPTH)-1:0] read_addr,
    output reg [WIDTH-1:0] read_data
);

    // Internal RAM array
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
            // Write data to the specified address
            internal_RAM[write_addr] <= write_data;
        end
    end

    // Read operation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_data <= {WIDTH{1'b0}}; // Clear read_data on reset
        end else if (read_en) begin
            // Read data from the specified address
            read_data <= internal_RAM[read_addr];
        end else begin
            read_data <= {WIDTH{1'b0}}; // Clear read_data if not reading
        end
    end

endmodule
