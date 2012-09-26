# -*- coding: utf-8 -*-
# ssp_read_traces.py
#
# Read traces for source_spec
# All the functions whose name is between "__" are intended to be private
# (c) 2012 Claudio Satriano <satriano@ipgp.fr>
from __future__ import division
import os
import logging
import shutil
import tarfile
import tempfile
from datetime import datetime
from obspy.core import Stream, read, UTCDateTime
from obspy.core.util import AttribDict
from obspy.xseed import Parser
from obspy.xseed.utils import SEEDParserException
from ssp_setup import ssp_exit

# TRACE MANIPULATION ----------------------------------------------------------
def __correct_traceid__(trace):
	try:
		import traceids
		traceid = traceids.__correct_traceid_dict__[trace.getId()]
		net, sta, loc, chan = traceid.split('.')
		trace.stats.network = net
		trace.stats.station = sta
		trace.stats.location = loc
		trace.stats.channel = chan
	except KeyError:
		pass

def __add_paz_and_coords__(trace, dataless):
	trace.stats.paz = None
	trace.stats.coords = None
	traceid = trace.getId()
	time = trace.stats.starttime
	# We first look into the dataless dictionary, if available
	if dataless != None:
		for sp in dataless.values():
			# Check first if our traceid is in the dataless file
			if not traceid in str(sp):
				continue	
			try:
				paz = sp.getPAZ(traceid, time)
				coords = AttribDict(sp.getCoordinates(traceid, time))
				# elevation is in meters in the dataless
				coords.elevation /= 1000
			except SEEDParserException, message:
				logging.error("%s time: %s" % (message, str(time)))
				pass
	try:
		trace.stats.paz = paz
		trace.stats.coords = coords
	except:
		pass
	# If we couldn't find any PAZ in the dataless dictionary,
	# we try to build the sensitivity from the
	# user2 and user3 header fields (ISNet format)
	if trace.stats.paz == None:
		try: 
			# instrument constants
			u2 = trace.stats.sac.user2 
			u3 = trace.stats.sac.user3
		 	if u2==-12345 or u3==-12345: raise AttributeError
			paz = AttribDict()
			paz.sensitivity = u3/u2
			paz.poles = []
			paz.zeros = []
			paz.gain = 1
			trace.stats.paz = paz
		except AttributeError:
			pass
	# Same thing for the station coordinates
	if trace.stats.coords == None:
		try: 
			stla = trace.stats.sac.stla
			stlo = trace.stats.sac.stlo
			stel = trace.stats.sac.stel
			# elevation is in meters in SAC header
			stel /= 1000
		 	if stla==-12345 or stlo==-12345 or stel==-12345:
				raise AttributeError
			coords = AttribDict()
			coords.elevation = stel
			coords.latitude = stla
			coords.longitude = stlo
			trace.stats.coords = coords
		except AttributeError:
			pass

def __add_instrtype__(trace):
	instrtype = None

	# First, try to get the instrtype from channel name
	chan = trace.stats.channel
	try: band_code = chan[0]
	except IndexError: band_code = None
	try: instr_code = chan[1]
	except IndexError: instr_code = None
	if instr_code == 'H' or instr_code == 'L':
		if band_code == 'E': 
			instrtype = 'shortp'
		if band_code == 'H': 
			instrtype = 'broadb'
	if instr_code == 'N': instrtype = 'acc'

	# If, not possible, let's see if there is an instrument
	# name in "kinst" (ISNet format)
	if instrtype == None:
		try:
			instr = trace.stats.sac.kinst
			if 'CMG-5T' in instr:
				instrtype = 'acc'
			if 'TRILLIUM' in instr:
				instrtype = 'broadb'
			if 'S13J' in instr:
				instrtype = 'shortp'
		except AttributeError:
			pass
	trace.stats.instrtype = instrtype
	
def __add_hypocenter__(trace, hypo):
	if hypo == None:
		# Try to get hypocenter information from the SAC header
		try:
			evla = trace.stats.sac.evla
			evlo = trace.stats.sac.evlo
			evdp = trace.stats.sac.evdp
			tori = trace.stats.sac.o
			begin = trace.stats.sac.b
			if evla == -12345 or evlo == -12345\
			   or evdp == -12345 or tori == -12345\
			   or begin == -12345:
				raise AttributeError
			hypo = AttribDict()
			hypo.latitude = evla
			hypo.longitude = evlo
			hypo.depth = evdp
			hypo.origin_time = trace.stats.starttime + tori - begin
			hypo.evid = hypo.origin_time.strftime("%Y%m%d_%H%M%S")
		except AttributeError:
			pass
	trace.stats.hypo = hypo

def __add_picks__(trace, picks):
	# TODO: try to get picks from SAC header
	if picks == None:
		trace.stats.picks = []
		return
	
	stat_picks=[]
	station = trace.stats.station
	for pick in picks:
		if pick.station == station:
			stat_picks.append(pick)
	trace.stats.picks = stat_picks
# -----------------------------------------------------------------------------



# FILE PARSING ----------------------------------------------------------------
def __read_dataless__(path):
	if path == None: return None

	logging.info('Reading dataless...')
	dataless=dict()
	if os.path.isdir(path):
		listing = os.listdir(path)
		for filename in listing:
			fullpath='%s/%s' % (path, filename)
			try:
				sp = Parser(fullpath)
				dataless[filename] = sp
			except IOError: continue
	logging.info('Reading dataless: done')
	return dataless

def __parse_hypocenter__(hypo_file):
	hypo = AttribDict()
	hypo.latitude = None
	hypo.longitude = None
	hypo.depth = None
	hypo.origin_time = None
	hypo.evid = None

	if hypo_file == None: return None

	try: fp = open(hypo_file)
	except: return None

	# Corinth hypocenter file format:
	# TODO: check file format
	line = fp.readline()
	# Skip the first line if it contains characters in the first 10 digits:
	if any(c.isalpha() for c in line[0:10]):
		line = fp.readline()
	fp.close()
	timestr = line[0:17]
	# There are two possible formats for the timestring.
	# We try both of them
	try:
		dt = datetime.strptime(timestr, '%y%m%d %H %M%S.%f')
	except ValueError:
		dt = datetime.strptime(timestr, '%y%m%d %H%M %S.%f')
	hypo.origin_time = UTCDateTime(dt)

	lat = float(line[17:20])
	lat_deg = float(line[21:26])
	hypo.latitude = lat + lat_deg/60
	lon = float(line[26:30])
	lon_deg = float(line[31:36])
	hypo.longitude = lon + lon_deg/60
	hypo.depth = float(line[36:42])
	evid = os.path.basename(hypo_file)
	hypo.evid = evid.replace('.phs','').replace('.h','').replace('.hyp','')

	return hypo

def __new_pick__():
	pick = AttribDict()
	pick.station  = None
	pick.flag     = None
	pick.phase    = None
	pick.polarity = None
	pick.quality  = None
	pick.time     = None
	return pick

def __parse_picks__(pick_file):
	if pick_file == None: return None

	try: fp = open(pick_file)
	except: return None

	picks = []

	# Corinth hypocenter file format:
	# TODO: check file format
	for line in fp.readlines():
		# remove newline
		line = line.replace('\n','')
		# skip separator and empty lines
		stripped_line = line.replace(' ','')
		if stripped_line == '10' or stripped_line == '': continue
		# Check if it is a pick line
		# 6th character should be alpha (phase name: P or S)
		if not line[5].isalpha():
			continue

		pick = __new_pick__()
		pick.station  = line[0:4]
		pick.flag     = line[4:5]
		pick.phase    = line[5:6]
		pick.polarity = line[6:7]
		pick.quality  = int(line[7:8])
		timestr       = line[9:24]
		dt = datetime.strptime(timestr, '%y%m%d%H%M%S.%f')
		pick.time = UTCDateTime(dt)

		picks.append(pick)

		try: stime = line[31:36]
		except: continue
		if stime.replace(' ','') == '': continue

		pick2 = __new_pick__()
		pick2.station  = pick.station
		pick2.flag     = line[36:37]
		pick2.phase    = line[37:38]
		pick2.polarity = line[38:39]
		pick2.quality  = int(line[39:40])
		pick2.time     = pick.time + float(stime)

		picks.append(pick2)

	fp.close()
	return picks


def __build_filelist__(path, filelist, tmpdir):
	if os.path.isdir(path):
		listing = os.listdir(path)
		for filename in listing:
			fullpath='%s/%s' % (path, filename)
			__build_filelist__(fullpath, filelist, tmpdir)
	else:
		try: 
			open(path)
		except IOError, message:
			logging.error(message)
			return
		if tarfile.is_tarfile(path) and tmpdir!=None:
			tar = tarfile.open(path)
			tar.extractall(path=tmpdir)
			tar.close()
		else:
			filelist.append(path)
# -----------------------------------------------------------------------------


# PATH DISCOVERY --------------------------------------------------------------
# We try to guess the path of the hypo and pick file from the data dir
# This applies (for the moment) only to the Corinth format
def __set_hypo_file_path__(config):
	if config.options.hypo_file != None:
		return
	# try with the basename of the datadir
	if os.path.isdir(config.args[0]):
		hypo_file = config.args[0] + '.phs.h'
		try:
			open(hypo_file)
			config.options.hypo_file = hypo_file
		except:
			pass
	return

def __set_pick_file_path__(config):
	if config.options.pick_file != None:
		return 
	# try with the basename of the datadir
	if os.path.isdir(config.args[0]):
		pick_file = config.args[0] + '.phs'
		try:
			open(pick_file)
			config.options.pick_file = pick_file
		except:
			pass
	return
# -----------------------------------------------------------------------------


# Public interface:
def read_traces(config):
	# read dataless	
	dataless = __read_dataless__(config.options.dataless)
	# parse hypocenter file
	__set_hypo_file_path__(config)
	hypo = __parse_hypocenter__(config.options.hypo_file)
	# parse pick file
	__set_pick_file_path__(config)
	picks = __parse_picks__(config.options.pick_file)

	# finally, read traces
	logging.info('Reading traces...')
	# phase 1: build a file list
	# ph 1.1: create a temporary dir and run '_build_filelist()'
	#         to move files to it and extract all tar archives
	tmpdir = tempfile.mkdtemp()
	filelist = []
	for arg in config.args:
		__build_filelist__(arg, filelist, tmpdir)
	# ph 1.2: rerun '_build_filelist()' in tmpdir to add to the
	#         filelist all the extraceted files
	listing = os.listdir(tmpdir)
	for filename in listing:
		fullpath='%s/%s' % (tmpdir, filename)
		__build_filelist__(fullpath, filelist, None)

	# phase 2: build a stream object from the file list
	st = Stream()
	for filename in filelist:
		try:
			tmpst = read(filename)
		except:
			logging.error('%s: Unable to read file as a trace: skipping' % filename)
			continue
		for trace in tmpst.traces:
			st.append(trace)
			__correct_traceid__(trace)
			__add_paz_and_coords__(trace, dataless)
			__add_instrtype__(trace)
			__add_hypocenter__(trace, hypo)
			__add_picks__(trace, picks)

	shutil.rmtree(tmpdir)
	logging.info('Reading traces: done')
	if len(st.traces) == 0:
		logging.info('No trace loaded') 
		ssp_exit()
	return st
