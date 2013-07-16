#!/usr/bin/env python
# -*- coding: utf8 -*- 
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
import os
from glob import glob
from collections import defaultdict
import cPickle as pickle
from optparse import OptionParser
from obspy.core import Stream
from lib.ssp_util import moment_to_mag, mag_to_moment
from lib.spectrum import Spectrum


usage = 'usage: %prog [options] residuals_dir'

parser = OptionParser(usage=usage);
parser.add_option('-m', '--min_spectra', dest='min_spectra', action='store', default='20',
        help='minimum number of spectra to compute residuals (default=20)', metavar='NUMBER')
parser.add_option('-p', '--plot', dest='plot', action='store_true', default=False,
        help='save residuals plots to file')
(options, args) = parser.parse_args()

if len(args) < 1:
    parser.print_usage(file=sys.stderr)
    sys.stderr.write("\tUse '-h' for help\n\n")
    sys.exit(1)

resdir = args[0]
min_spectra = float(options.min_spectra)

residual_dict = defaultdict(Stream)
for resfile in glob(os.path.join(resdir, '*-res*.pickle')):
    residual_st = pickle.load(open(resfile, 'rb'))
    for spec in residual_st:
        residual_dict[spec.id].append(spec)

residual_mean = Stream()
for stat_id in sorted(residual_dict.keys()):
    if len(residual_dict[stat_id]) < min_spectra:
        continue
    print stat_id

    res = residual_dict[stat_id]

    freqs_min = [spec.get_freq().min() for spec in res]
    freqs_max = [spec.get_freq().max() for spec in res]
    freq_min = min(freqs_min)
    freq_max = max(freqs_max)

    spec_mean = Spectrum()
    spec_mean.stats.begin = freq_min
    spec_mean.stats.delta = res[0].stats.delta
    spec_mean.stats.station = res[0].stats.station
    spec_mean.data_mag = None
    for n, spec in enumerate(res):
        spec_slice = spec.slice(freq_min, freq_max, pad=True, fill_value=mag_to_moment(0))
        spec_slice.data_mag = moment_to_mag(spec_slice.data)
        if spec_mean.data_mag is None:
            spec_mean.data_mag = spec_slice.data_mag
        else:
            spec_mean.data_mag += spec_slice.data_mag
    spec_mean.data_mag /= n
    spec_mean.data = mag_to_moment(spec_mean.data_mag)

    residual_mean.append(spec_mean)

    ### plot traces ###
    if options.plot:
        stnm = spec_mean.stats.station
        figurefile = os.path.join(resdir, stnm + '-res.png')
        fig = plt.figure(dpi=160)
        for spec in res:
            plt.semilogx(spec.get_freq(), spec.data_mag, 'b-')
        plt.semilogx(spec_mean.get_freq(), spec_mean.data_mag, 'r-')
        plt.xlabel('frequency (Hz)')
        plt.ylabel('residual amplitude (obs - synth) in magnitude unit')
        plt.title('residuals : ' + stnm + ', ' + str(len(res)) + ' records.')
        fig.savefig(figurefile, bbox_inches='tight')

### writes the mean residuals (the stations corrections) ###
with open(os.path.join(resdir, 'residual_mean.pickle'), 'wb') as fp:
    pickle.dump(residual_mean, fp)
