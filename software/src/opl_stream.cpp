#include "opl_stream.h"

#include <cstddef>
#include <cstring>

#include "opl_hw.h"
#include "timer_ps.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xuartps.h"

namespace {

constexpr u32 kCliBaud = 115200;
constexpr u32 kStreamBaud = 921600;
constexpr u8 kSync0 = 0x4F;
constexpr u8 kSync1 = 0x50;
constexpr u8 kTypeHello = 0x01;
constexpr u8 kTypeEnterStream = 0x02;
constexpr u8 kTypeOplEvent = 0x03;
constexpr u8 kTypeStop = 0x04;
constexpr u8 kTypeResetOpl = 0x05;
constexpr u8 kTypeStatus = 0x06;
constexpr u8 kTypeExitStream = 0x07;
constexpr u8 kTypeUploadBegin = 0x08;
constexpr u8 kTypeUploadChunk = 0x09;
constexpr u8 kTypeUploadEnd = 0x0A;
constexpr u8 kTypePlayBuffered = 0x0B;
constexpr u8 kTypeError = 0x7F;
constexpr u8 kResponseMask = 0x80;
constexpr u8 kVersionMajor = 1;
constexpr u8 kVersionMinor = 1;
constexpr size_t kFramePayloadMax = 192;
constexpr size_t kQueueCapacity = 2048;
constexpr size_t kSongBufferSize = 8 * 1024 * 1024;
constexpr u64 kGlobalTimerCorrection = 4;
constexpr u64 kGlobalTimerCountsPerSecond = XPAR_CPU_CORE_CLOCK_FREQ_HZ / 2;
constexpr u32 kBufferedTimerDelayNum = 4;
constexpr u32 kBufferedTimerDelayDen = 5;
using XTime = u64;
extern "C" void XTime_GetTime(XTime *time_value);

struct QueuedWrite {
	u32 delay_us;
	u8 bank;
	u8 reg;
	u8 value;
};

struct QueueState {
	QueuedWrite items[kQueueCapacity];
	u16 head = 0;
	u16 tail = 0;
	u16 count = 0;
};

struct BufferedEvent {
	u32 delay_us;
	u8 count;
	const u8 *writes;
	u32 size_bytes;
};

struct FrameParser {
	enum State {
		WAIT_SYNC0,
		WAIT_SYNC1,
		READ_TYPE,
		READ_LEN0,
		READ_LEN1,
		READ_PAYLOAD,
		READ_CHECKSUM
	} state = WAIT_SYNC0;

	u8 type = 0;
	u16 length = 0;
	u16 payload_index = 0;
	u8 payload[kFramePayloadMax];
};

struct BufferedSongState {
	u8 data[kSongBufferSize];
	u32 expected_size = 0;
	u32 loaded_size = 0;
	u32 play_offset = 0;
	bool upload_active = false;
	bool loaded_ready = false;
	bool playback_active = false;
};

XUartPs g_uart;
bool g_uart_ready = false;
QueueState g_queue;
bool g_stream_playback_armed = false;
u64 g_stream_next_deadline_us = 0;
BufferedSongState g_song;

u64 now_us()
{
	XTime ticks;
	XTime_GetTime(&ticks);
	return static_cast<u64>((ticks * 1000000ULL * kGlobalTimerCorrection) / kGlobalTimerCountsPerSecond);
}

bool uart_init(u32 baud_rate)
{
	if (!g_uart_ready) {
		XUartPs_Config *config = XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR);
		if (config == nullptr) {
			return false;
		}

		int status = XUartPs_CfgInitialize(&g_uart, config, config->BaseAddress);
		if (status != XST_SUCCESS) {
			return false;
		}

		XUartPs_SetOperMode(&g_uart, XUARTPS_OPER_MODE_NORMAL);
		g_uart_ready = true;
	}

	return XUartPs_SetBaudRate(&g_uart, baud_rate) == XST_SUCCESS;
}

bool uart_read_byte(u8 *value)
{
	return XUartPs_Recv(&g_uart, value, 1) == 1;
}

void uart_write(const u8 *data, size_t length)
{
	if (length == 0) {
		return;
	}

	XUartPs_Send(&g_uart, const_cast<u8 *>(data), static_cast<u32>(length));
	while (XUartPs_IsSending(&g_uart) != 0) {
	}
}

u8 calc_checksum(u8 type, u16 length, const u8 *payload)
{
	u32 sum = type;
	sum += static_cast<u8>(length & 0xFF);
	sum += static_cast<u8>((length >> 8) & 0xFF);
	for (u16 i = 0; i < length; ++i) {
		sum += payload[i];
	}
	return static_cast<u8>(sum & 0xFF);
}

void send_frame(u8 type, const u8 *payload, u16 length)
{
	u8 header[5];
	header[0] = kSync0;
	header[1] = kSync1;
	header[2] = type;
	header[3] = static_cast<u8>(length & 0xFF);
	header[4] = static_cast<u8>((length >> 8) & 0xFF);
	u8 checksum = calc_checksum(type, length, payload);

	uart_write(header, sizeof(header));
	if (length > 0) {
		uart_write(payload, length);
	}
	uart_write(&checksum, 1);
}

void send_ok(u8 request_type)
{
	send_frame(static_cast<u8>(request_type | kResponseMask), nullptr, 0);
}

void send_error(u8 code)
{
	send_frame(kTypeError, &code, 1);
}

void send_hello()
{
	u8 payload[16];
	payload[0] = kVersionMajor;
	payload[1] = kVersionMinor;
	payload[2] = static_cast<u8>(kQueueCapacity & 0xFF);
	payload[3] = static_cast<u8>((kQueueCapacity >> 8) & 0xFF);
	payload[4] = static_cast<u8>(kStreamBaud & 0xFF);
	payload[5] = static_cast<u8>((kStreamBaud >> 8) & 0xFF);
	payload[6] = static_cast<u8>((kStreamBaud >> 16) & 0xFF);
	payload[7] = static_cast<u8>((kStreamBaud >> 24) & 0xFF);
	payload[8] = static_cast<u8>(kCliBaud & 0xFF);
	payload[9] = static_cast<u8>((kCliBaud >> 8) & 0xFF);
	payload[10] = static_cast<u8>((kCliBaud >> 16) & 0xFF);
	payload[11] = static_cast<u8>((kCliBaud >> 24) & 0xFF);
	payload[12] = static_cast<u8>(kSongBufferSize & 0xFF);
	payload[13] = static_cast<u8>((kSongBufferSize >> 8) & 0xFF);
	payload[14] = static_cast<u8>((kSongBufferSize >> 16) & 0xFF);
	payload[15] = static_cast<u8>((kSongBufferSize >> 24) & 0xFF);
	send_frame(static_cast<u8>(kTypeHello | kResponseMask), payload, sizeof(payload));
}

bool queue_push(u32 delay_us, u8 bank, u8 reg, u8 value)
{
	if (g_queue.count >= kQueueCapacity) {
		return false;
	}

	g_queue.items[g_queue.tail].delay_us = delay_us;
	g_queue.items[g_queue.tail].bank = bank;
	g_queue.items[g_queue.tail].reg = reg;
	g_queue.items[g_queue.tail].value = value;
	g_queue.tail = static_cast<u16>((g_queue.tail + 1) % kQueueCapacity);
	++g_queue.count;
	return true;
}

bool queue_peek(QueuedWrite *item)
{
	if (g_queue.count == 0) {
		return false;
	}

	*item = g_queue.items[g_queue.head];
	return true;
}

bool queue_pop(QueuedWrite *item)
{
	if (!queue_peek(item)) {
		return false;
	}

	g_queue.head = static_cast<u16>((g_queue.head + 1) % kQueueCapacity);
	--g_queue.count;
	return true;
}

void queue_clear()
{
	g_queue.head = 0;
	g_queue.tail = 0;
	g_queue.count = 0;
	g_stream_playback_armed = false;
	g_stream_next_deadline_us = 0;
}

void buffered_reset_metadata()
{
	g_song.expected_size = 0;
	g_song.loaded_size = 0;
	g_song.play_offset = 0;
	g_song.upload_active = false;
	g_song.loaded_ready = false;
	g_song.playback_active = false;
}

void buffered_stop_playback()
{
	g_song.play_offset = 0;
	g_song.playback_active = false;
}

void stop_all_playback()
{
	queue_clear();
	buffered_stop_playback();
}

bool parse_buffered_event(u32 offset, BufferedEvent *event)
{
	if (offset + 5 > g_song.loaded_size) {
		return false;
	}

	const u8 *data = &g_song.data[offset];
	event->delay_us = static_cast<u32>(data[0])
		| (static_cast<u32>(data[1]) << 8)
		| (static_cast<u32>(data[2]) << 16)
		| (static_cast<u32>(data[3]) << 24);
	event->count = data[4];
	if (event->count == 0) {
		return false;
	}

	event->size_bytes = static_cast<u32>(5 + event->count * 3);
	if (offset + event->size_bytes > g_song.loaded_size) {
		return false;
	}

	event->writes = data + 5;
	return true;
}

bool validate_buffered_song()
{
	u32 offset = 0;
	while (offset < g_song.loaded_size) {
		BufferedEvent event;
		if (!parse_buffered_event(offset, &event)) {
			return false;
		}
		offset += event.size_bytes;
	}
	return offset == g_song.loaded_size;
}

void send_status()
{
	u8 payload[5];
	u16 free_slots = static_cast<u16>(kQueueCapacity - g_queue.count);
	bool playing = g_stream_playback_armed || g_queue.count != 0 || g_song.playback_active;
	payload[0] = static_cast<u8>(free_slots & 0xFF);
	payload[1] = static_cast<u8>((free_slots >> 8) & 0xFF);
	payload[2] = static_cast<u8>(g_queue.count & 0xFF);
	payload[3] = static_cast<u8>((g_queue.count >> 8) & 0xFF);
	payload[4] = playing ? 1 : 0;
	send_frame(static_cast<u8>(kTypeStatus | kResponseMask), payload, sizeof(payload));
}

void service_stream_playback()
{
	if (!g_stream_playback_armed) {
		QueuedWrite first;
		if (!queue_peek(&first)) {
			return;
		}
		g_stream_next_deadline_us = now_us() + first.delay_us;
		g_stream_playback_armed = true;
	}

	u64 current_us = now_us();
	while (g_stream_playback_armed && current_us >= g_stream_next_deadline_us) {
		QueuedWrite item;
		if (!queue_pop(&item)) {
			g_stream_playback_armed = false;
			return;
		}

		opl_write_reg(item.reg, item.value, item.bank);

		QueuedWrite next;
		if (!queue_peek(&next)) {
			g_stream_playback_armed = false;
			return;
		}

		g_stream_next_deadline_us += next.delay_us;
		current_us = now_us();
	}
}

void service_buffered_playback()
{
	// Buffered playback is executed synchronously in play_buffered_song().
}

bool enqueue_opl_event(const u8 *payload, u16 length)
{
	if (length < 5) {
		return false;
	}

	u32 delay_us = static_cast<u32>(payload[0])
		| (static_cast<u32>(payload[1]) << 8)
		| (static_cast<u32>(payload[2]) << 16)
		| (static_cast<u32>(payload[3]) << 24);
	u8 count = payload[4];
	if (length != static_cast<u16>(5 + count * 3)) {
		return false;
	}

	if ((kQueueCapacity - g_queue.count) < count) {
		send_error(2);
		send_status();
		return true;
	}

	for (u8 i = 0; i < count; ++i) {
		u8 bank = payload[5 + i * 3 + 0];
		u8 reg = payload[5 + i * 3 + 1];
		u8 value = payload[5 + i * 3 + 2];
		if (!queue_push(i == 0 ? delay_us : 0, bank, reg, value)) {
			send_error(2);
			return true;
		}
	}

	return true;
}

bool begin_upload(const u8 *payload, u16 length)
{
	if (length != 4) {
		send_error(5);
		return false;
	}

	u32 expected_size = static_cast<u32>(payload[0])
		| (static_cast<u32>(payload[1]) << 8)
		| (static_cast<u32>(payload[2]) << 16)
		| (static_cast<u32>(payload[3]) << 24);
	if (expected_size == 0 || expected_size > kSongBufferSize) {
		send_error(6);
		return false;
	}

	stop_all_playback();
	buffered_reset_metadata();
	g_song.expected_size = expected_size;
	g_song.upload_active = true;
	send_ok(kTypeUploadBegin);
	return true;
}

bool upload_chunk(const u8 *payload, u16 length)
{
	if (!g_song.upload_active) {
		send_error(7);
		return false;
	}

	if (g_song.loaded_size + length > g_song.expected_size) {
		send_error(8);
		return false;
	}

	std::memcpy(&g_song.data[g_song.loaded_size], payload, length);
	g_song.loaded_size += length;
	send_ok(kTypeUploadChunk);
	return true;
}

bool end_upload()
{
	if (!g_song.upload_active) {
		send_error(7);
		return false;
	}

	if (g_song.loaded_size != g_song.expected_size) {
		send_error(9);
		return false;
	}

	if (!validate_buffered_song()) {
		buffered_reset_metadata();
		send_error(10);
		return false;
	}

	g_song.upload_active = false;
	g_song.loaded_ready = true;
	send_ok(kTypeUploadEnd);
	return true;
}

bool play_buffered_song()
{
	if (!g_song.loaded_ready || g_song.loaded_size == 0) {
		send_error(11);
		return false;
	}

	queue_clear();
	buffered_stop_playback();
	opl_reset_core();
	g_song.play_offset = 0;
	g_song.playback_active = true;

	while (g_song.play_offset < g_song.loaded_size) {
		BufferedEvent current_event;
		if (!parse_buffered_event(g_song.play_offset, &current_event)) {
			buffered_stop_playback();
			send_error(10);
			return false;
		}

		if (current_event.delay_us > 0) {
			TimerDelay((current_event.delay_us * kBufferedTimerDelayNum) / kBufferedTimerDelayDen);
		}

		for (u8 i = 0; i < current_event.count; ++i) {
			const u8 *write = current_event.writes + (i * 3);
			opl_write_reg(write[1], write[2], write[0]);
		}

		g_song.play_offset += current_event.size_bytes;
	}

	buffered_stop_playback();
	send_ok(kTypePlayBuffered);
	return true;
}

bool handle_frame(u8 type, const u8 *payload, u16 length, bool *keep_running)
{
	switch (type) {
	case kTypeHello:
		send_hello();
		return true;
	case kTypeEnterStream:
		stop_all_playback();
		opl_reset_core();
		send_ok(kTypeEnterStream);
		send_status();
		return true;
	case kTypeOplEvent:
		return enqueue_opl_event(payload, length);
	case kTypeStop:
		stop_all_playback();
		opl_reset_core();
		send_ok(kTypeStop);
		send_status();
		return true;
	case kTypeResetOpl:
		stop_all_playback();
		opl_reset_core();
		send_ok(kTypeResetOpl);
		return true;
	case kTypeStatus:
		send_status();
		return true;
	case kTypeExitStream:
		stop_all_playback();
		opl_reset_core();
		send_ok(kTypeExitStream);
		*keep_running = false;
		return true;
	case kTypeUploadBegin:
		return begin_upload(payload, length);
	case kTypeUploadChunk:
		return upload_chunk(payload, length);
	case kTypeUploadEnd:
		return end_upload();
	case kTypePlayBuffered:
		return play_buffered_song();
	default:
		send_error(1);
		return false;
	}
}

bool feed_parser(FrameParser *parser, u8 byte, bool *keep_running)
{
	switch (parser->state) {
	case FrameParser::WAIT_SYNC0:
		if (byte == kSync0) {
			parser->state = FrameParser::WAIT_SYNC1;
		}
		break;
	case FrameParser::WAIT_SYNC1:
		if (byte == kSync1) {
			parser->state = FrameParser::READ_TYPE;
		} else if (byte != kSync0) {
			parser->state = FrameParser::WAIT_SYNC0;
		}
		break;
	case FrameParser::READ_TYPE:
		parser->type = byte;
		parser->state = FrameParser::READ_LEN0;
		break;
	case FrameParser::READ_LEN0:
		parser->length = byte;
		parser->state = FrameParser::READ_LEN1;
		break;
	case FrameParser::READ_LEN1:
		parser->length |= static_cast<u16>(byte) << 8;
		parser->payload_index = 0;
		if (parser->length > kFramePayloadMax) {
			parser->state = FrameParser::WAIT_SYNC0;
			send_error(3);
			break;
		}
		parser->state = parser->length == 0 ? FrameParser::READ_CHECKSUM : FrameParser::READ_PAYLOAD;
		break;
	case FrameParser::READ_PAYLOAD:
		parser->payload[parser->payload_index++] = byte;
		if (parser->payload_index >= parser->length) {
			parser->state = FrameParser::READ_CHECKSUM;
		}
		break;
	case FrameParser::READ_CHECKSUM: {
		u8 expected = calc_checksum(parser->type, parser->length, parser->payload);
		if (expected == byte) {
			handle_frame(parser->type, parser->payload, parser->length, keep_running);
		} else {
			send_error(4);
		}
		parser->state = FrameParser::WAIT_SYNC0;
		break;
	}
	}

	return true;
}

} // namespace

int stream_session(void)
{
	if (!uart_init(kStreamBaud)) {
		xil_printf("UART init failed.\r\n");
		return -1;
	}

	queue_clear();
	buffered_reset_metadata();
	opl_reset_core();
	send_hello();

	FrameParser parser;
	bool keep_running = true;
	while (keep_running) {
		bool did_work = false;

		u8 byte = 0;
		while (uart_read_byte(&byte)) {
			feed_parser(&parser, byte, &keep_running);
			did_work = true;
		}

		service_stream_playback();
		service_buffered_playback();
		if (g_stream_playback_armed || g_queue.count != 0 || g_song.playback_active) {
			did_work = true;
		}

		if (!did_work) {
			TimerDelay(50);
		}
	}

	uart_init(kCliBaud);
	return 0;
}
