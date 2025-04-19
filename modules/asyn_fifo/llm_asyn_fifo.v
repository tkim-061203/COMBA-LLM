module dual_port_RAM #(parameter WIDTH = 8, parameter DEPTH = 16) (
    input wire wclk,
    input wire wenc,
    input wire [$clog2(DEPTH)-1:0] waddr,
    input wire [WIDTH-1:0] wdata,
    input wire rclk,
    input wire renc,
    input wire [$clog2(DEPTH)-1:0] raddr,
    output reg [WIDTH-1:0] rdata
);

    reg [WIDTH-1:0] RAM_MEM [0:DEPTH-1];

    always @(posedge wclk) begin
        if (wenc) begin
            RAM_MEM[waddr] <= wdata;
        end
    end

    always @(posedge rclk) begin
        if (renc) begin
            rdata <= RAM_MEM[raddr];
        end
    end

endmodule


module asyn_fifo #(parameter WIDTH = 8, parameter DEPTH = 16) (
    input wire wclk,
    input wire rclk,
    input wire wrstn,
    input wire rrstn,
    input wire winc,
    input wire rinc,
    input wire [WIDTH-1:0] wdata,
    output wire wfull,
    output wire rempty,
    output reg [WIDTH-1:0] rdata
);

    localparam ADDR_WIDTH = $clog2(DEPTH);

    reg [ADDR_WIDTH:0] waddr_bin;
    reg [ADDR_WIDTH:0] raddr_bin;
    reg [ADDR_WIDTH:0] wptr;
    reg [ADDR_WIDTH:0] rptr;
    reg [ADDR_WIDTH:0] wptr_buff;
    reg [ADDR_WIDTH:0] rptr_buff;
    reg [ADDR_WIDTH:0] rptr_syn;
    reg [ADDR_WIDTH:0] wptr_syn;

    wire wen = winc && !wfull;
    wire ren = rinc && !rempty;

    // Write address logic
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            waddr_bin <= 0;
        end else if (wen) begin
            waddr_bin <= waddr_bin + 1;
        end
    end

    // Read address logic
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            raddr_bin <= 0;
        end else if (ren) begin
            raddr_bin <= raddr_bin + 1;
        end
    end

    // Gray code conversion for write pointer
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            wptr <= 0;
        end else begin
            wptr <= (waddr_bin >> 1) ^ waddr_bin;
        end
    end

    // Gray code conversion for read pointer
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            rptr <= 0;
        end else begin
            rptr <= (raddr_bin >> 1) ^ raddr_bin;
        end
    end

    // Synchronize read pointer
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            rptr_buff <= 0;
        end else begin
            rptr_buff <= rptr;
        end
    end

    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            rptr_syn <= 0;
        end else begin
            rptr_syn <= rptr_buff;
        end
    end

    // Synchronize write pointer
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn) begin
            wptr_buff <= 0;
        end else begin
            wptr_buff <= wptr;
        end
    end

    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn) begin
            wptr_syn <= 0;
        end else begin
            wptr_syn <= wptr_buff;
        end
    end

    // Full and empty logic
    assign wfull = (wptr == {~rptr_syn[ADDR_WIDTH:ADDR_WIDTH-1], rptr_syn[ADDR_WIDTH-2:0]});
    assign rempty = (rptr == wptr_syn);

    // Dual-port RAM instantiation
    dual_port_RAM #(.WIDTH(WIDTH), .DEPTH(DEPTH)) ram_inst (
        .wclk(wclk),
        .wenc(wen),
        .waddr(waddr_bin[ADDR_WIDTH-1:0]),
        .wdata(wdata),
        .rclk(rclk),
        .renc(ren),
        .raddr(raddr_bin[ADDR_WIDTH-1:0]),
        .rdata(rdata)
    );

endmodule
