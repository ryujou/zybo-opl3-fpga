/*
 * main.cpp
 *
 *  Created on: Aug 5, 2015
 *      Author: greg
 */
#include <iostream>
#include "xilmfs.h"
#include "xparameters.h"
#include "ssm2603.h"
#include "timer_ps.h"
#include "imfplay.h"
#include "opl_stream.h"

#define CMD_BUF_LEN	256

using namespace std;

static bool g_mfs_ready = false;

static void ensure_mfs_ready() {
	if (!g_mfs_ready) {
		mfs_init_genimage(2660000, (char *) 0x10000000, MFSINIT_IMAGE);
		g_mfs_ready = true;
	}
}

void parseCmd(char *cmd) {
	char *token;

	token = strtok(cmd, " ");
	if (token == nullptr) {
		return;
	}

	if (strncmp(token, "help", 4) == 0) {
		cout << "ls - list files" << endl;
		cout << "play FILENAME - play a file" << endl;
		cout << "stream - enter real-time MIDI stream mode" << endl;
	}
	else if (strncmp(token, "ls", 2) == 0) {
		ensure_mfs_ready();
		mfs_ls();
	}
	else if (strncmp(token, "play", 4) == 0) {
		token = strtok(NULL, " ");
		ensure_mfs_ready();
		if (mfs_exists_file(token) == 0) {
			cout << token << " not found." << endl;
		}
		else {
			imfplay(token);
			cout << endl;
		}
	}
	else if (strncmp(token, "stream", 6) == 0) {
		cout << "Entering stream mode..." << endl;
		stream_session();
		cout << "Returned to command mode." << endl;
	}
}

int main() {
	char cmd[CMD_BUF_LEN];
	char singleChar;

	TimerInitialize(XPAR_SCUTIMER_BASEADDR); // accurate timer
	ssm2603_init(); // ZYBO DAC init, config is over i2c directly connected to PS
	stream_session();

	cout << "Welcome to the OPL3 FPGA" << endl << endl;
	cout << "Type 'help' for a list of commands" << endl;

	while (1) {
		memset(cmd, 0, CMD_BUF_LEN);
		cout << ">" << flush;

		for (int i = 0; i < CMD_BUF_LEN;) {
			singleChar = inbyte();
			outbyte(singleChar);

			if (singleChar == 0x8 || singleChar == 0x7F) {// backspace
				if (i > 0) {
					--i;
				}
				continue;
			}

			if (singleChar == '\r') {
				cout << endl;
				parseCmd(cmd);
				break;
			}
			else {
				cmd[i] = singleChar;
			}
			++i;
		}
	}
}
