#*******************************************************************************
#   +html+<pre>
#
#   FILENAME: Makefile
#   AUTHOR: Greg Taylor      CREATION DATE: 8 Aug 2015
#
#   DESCRIPTION:
#	1. Source the Vivado and Vitis settings so all the build tools are in your
#      path.
#      E.g. source /opt/Xilinx/Vivado/2025.2/settings64.sh
#           source /opt/Xilinx/Vitis/2025.2/settings64.sh
#
#	2. Run 'make' to build all the FPGA and software necessary to run the OPL3.
#
#	3. Recommended dev flow is JTAG download of bitstream + ELF.
#
#	4. Connect the USB data cable to the board and PC.
#
#	5. Use the Python USB host app for MIDI/VGM/VGZ upload and playback.
#
#	6. For CLI/debug only, UART still uses 115200 8-N-1.
#
#	7. Power on the ZYBO. In your CLI terminal you should see:
#          Welcome to the OPL3 FPGA
#
#          Type 'help' for a list of commands
#          >
#
#	   Enjoy!
#
#   CHANGE HISTORY:
#   8 Aug 2015        Greg Taylor
#       Initial version
#
#   Copyright (C) 2014 Greg Taylor <gtaylor@sonic.net>
#
#   This file is part of OPL3 FPGA.
#
#   OPL3 FPGA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Lesser General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   OPL3 FPGA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public License
#   along with OPL3 FPGA.  If not, see <http://www.gnu.org/licenses/>.
#
#   Original Java Code:
#   Copyright (C) 2008 Robson Cozendey <robson@cozendey.com>
#
#   Original C++ Code:
#   Copyright (C) 2012  Steffen Ohrendorf <steffen.ohrendorf@gmx.de>
#
#   Some code based on forum posts in:
#   http://forums.submarine.org.uk/phpBB/viewforum.php?f=9,
#   Copyright (C) 2010-2013 by carbon14 and opl3
#
#******************************************************************************
sd: all BOOT.bin
qspi-image: BOOT.bin

qspi-program: BOOT.bin
	powershell -ExecutionPolicy Bypass -File software/qspi/program_qspi.ps1

all:
	cd fpga && make bitstream
	vitis -s software/vitis_builder.py
	cd software/opl3dro && mfsgen -c *.dro

clean:
	cd fpga && make clean
	rm -rf vitis_project BOOT.bin logs software/opl3dro/filesystem.mfs
	rm -rf vivado* .Xil

BOOT.bin:
	bootgen -image software/bif/imfplay_port.bif -arch zynq -o BOOT.bin -w on

program:
	cd fpga && make program
