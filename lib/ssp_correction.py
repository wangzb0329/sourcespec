# -*- coding: utf8 -*-
# ssp_correction.py
#
# Spectral station correction calculated from ssp_residuals.py
# (c) 2013 Claudio Satriano <satriano@ipgp.fr>,
#          Agnes Chounet <chounet@ipgp.fr>
import cPickle as pickle
import logging
from ssp_util import moment_to_mag, mag_to_moment

def station_correction(spec_st, config):
    res_filepath = config.residuals_filepath
    residual = pickle.load(open(res_filepath,'rb'))

    for spec in [spec for spec in spec_st if (spec.stats.channel=='H')]:
        station = spec.stats.station
        if station in set(x.stats.station for x in residual):
            corr = residual.select(station=station)[0]
            fmin = spec.get_freq().min()
            fmax = spec.get_freq().max()
            corr = corr.slice(fmin, fmax)
            corr.data_mag = moment_to_mag(corr.data)
            spec.data_mag -= corr.data_mag
            spec.data = mag_to_moment(spec.data_mag)

            logging.info('%s corrected, frequency range is: %f %f' % (spec.id, fmin, fmax))
    return spec_st