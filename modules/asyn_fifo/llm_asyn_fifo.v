module dual_port_RAM #(parameter DEPTH = 16, parameter WIDTH = 8) (
    input wire wclk,
    input wire wenc,
    input wire [ADDR_WIDTH-1:0] waddr,
    input wire [WIDTH-1:0] wdata,
    input wire rclk,
    input wire renc,
    input wire [ADDR_WIDTH-1:0] raddr,
    output reg [WIDTH-1:0] rdata
);

    localparam ADDR_WIDTH = $clog2(DEPTH);
    reg [WIDTH-1:0] RAM_MEM [0:DEPTH-1];

    // Write operation
    always @(posedge wclk) begin
        if (wenc) begin
            RAM_MEM[waddr] <= wdata;
        end
    end

    // Read operation
    always @(posedge rclk) begin
        if (renc) begin
            rdata <= RAM_MEM[raddr];
        end
    end

endmodule

module asyn_fifo #(parameter DEPTH = 16, parameter WIDTH = 8) (
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

    // Dual-port RAM instantiation
    wire [WIDTH-1:0] ram_data_out;
    wire [ADDR_WIDTH-1:0] waddr;
    wire [ADDR_WIDTH-1:0] raddr;
    wire wen;
    wire ren;

    dual_port_RAM #(.DEPTH(DEPTH), .WIDTH(WIDTH)) ram (
        .wclk(wclk),
        .wenc(wen),
        .waddr(waddr),
        .wdata(wdata),
        .rclk(rclk),
        .renc(ren),
        .raddr(raddr),
        .rdata(ram_data_out)
    );

    // Read address binary and gray code
    reg [ADDR_WIDTH:0] raddr_bin;
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn)
            raddr_bin <= 0;
        else if (!rempty && rinc)
            raddr_bin <= raddr_bin + 1;
    end

    wire [ADDR_WIDTH-1:0] raddr_gray = raddr_bin ^ (raddr_bin >> 1);

    // Read pointer
    reg [ADDR_WIDTH:0] rptr;
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn)
            rptr <= 0;
        else
            rptr <= raddr_gray;
    end

    // Read pointer buffer
    reg [ADDR_WIDTH:0] rptr_buff;
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn)
            rptr_buff <= 0;
        else
            rptr_buff <= rptr;
    end

    // Read pointer synchronizer
    reg [ADDR_WIDTH:0] rptr_syn;
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn)
            rptr_syn <= 0;
        else
            rptr_syn <= rptr_buff;
    end

    // Read enable logic
    assign ren = rinc && !rempty;

    // Write address binary and gray code
    reg [ADDR_WIDTH:0] waddr_bin;
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn)
            waddr_bin <= 0;
        else if (!wfull && winc)
            waddr_bin <= waddr_bin + 1;
    end

    wire [ADDR_WIDTH-1:0] waddr_gray = waddr_bin ^ (waddr_bin >> 1);

    // Write pointer
    reg [ADDR_WIDTH:0] wptr;
    always @(posedge wclk or negedge wrstn) begin
        if (!wrstn)
            wptr <= 0;
        else
            wptr <= waddr_gray;
    end

    // Write pointer buffer
    reg [ADDR_WIDTH:0] wptr_buff;
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn)
            wptr_buff <= 0;
        else
            wptr_buff <= wptr;
    end

    // Write pointer synchronizer
    reg [ADDR_WIDTH:0] wptr_syn;
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn)
            wptr_syn <= 0;
        else
            wptr_syn <= wptr_buff;
    end

    // Write enable logic
    assign wen = winc && !wfull;

    // Full and empty signals
    assign wfull = (wptr[ADDR_WIDTH-1:1] == ~rptr_syn[ADDR_WIDTH-1:1]) && (wptr[ADDR_WIDTH-2:0] == rptr_syn[ADDR_WIDTH-2:0]);
    assign rempty = (rptr == wptr_syn);

    // Update rdata with the correct RAM output
    always @(posedge rclk or negedge rrstn) begin
        if (!rrstn)
            rdata <= 0;
        else if (ren)
            rdata <= ram_data_out;
    end

endmodule
