import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.signal
import scipy.stats

from ..signal import (
    signal_findpeaks,
    signal_plot,
    signal_sanitize,
    signal_smooth,
    signal_zerocrossings,
)


def ecg_findpeaks(
    ecg_cleaned, sampling_rate=1000, method="neurokit", show=False, **kwargs
):
    """**Locate R-peaks**

    Low-level function used by :func:`ecg_peaks` to identify R-peaks in an ECG signal using a
    different set of algorithms. Use the main function and see its documentation for details.

    Parameters
    ----------
    ecg_cleaned : Union[list, np.array, pd.Series]
        See :func:`ecg_peaks()`.
    sampling_rate : int
        See :func:`ecg_peaks()`.
    method : string
        See :func:`ecg_peaks()`.
    show : bool
        If ``True``, will return a plot to visualizing the thresholds used in the algorithm.
        Useful for debugging.
    **kwargs
        Additional keyword arguments, usually specific for each ``method``.

    Returns
    -------
    info : dict
        A dictionary containing additional information, in this case the
        samples at which R-peaks occur, accessible with the key ``"ECG_R_Peaks"``.

    See Also
    --------
    ecg_peaks, .signal_fixpeaks

    """
    # Try retrieving right column
    if isinstance(ecg_cleaned, pd.DataFrame):
        try:
            ecg_cleaned = ecg_cleaned["ECG_Clean"]
        except (NameError, KeyError):
            try:
                ecg_cleaned = ecg_cleaned["ECG_Raw"]
            except (NameError, KeyError):
                ecg_cleaned = ecg_cleaned["ECG"]

    # Sanitize input
    ecg_cleaned = signal_sanitize(ecg_cleaned)
    method = method.lower()  # remove capitalised letters

    # Run peak detection algorithm
    try:
        func = _ecg_findpeaks_findmethod(method)
        rpeaks = func(ecg_cleaned, sampling_rate=sampling_rate, show=show, **kwargs)
    except ValueError as error:
        raise error

    # Prepare output.
    info = {"ECG_R_Peaks": rpeaks}

    return info


# Returns the peak detector function by name
def _ecg_findpeaks_findmethod(method):
    if method in ["nk", "nk2", "neurokit", "neurokit2"]:
        return _ecg_findpeaks_neurokit
    elif method in ["pantompkins", "pantompkins1985"]:
        return _ecg_findpeaks_pantompkins
    elif method in ["nabian", "nabian2018"]:
        return _ecg_findpeaks_nabian2018
    elif method in ["gamboa2008", "gamboa"]:
        return _ecg_findpeaks_gamboa
    elif method in ["ssf", "slopesumfunction"]:
        return _ecg_findpeaks_ssf
    elif method in ["zong", "zong2003", "wqrs"]:
        return _ecg_findpeaks_zong
    elif method in ["hamilton", "hamilton2002"]:
        return _ecg_findpeaks_hamilton
    elif method in ["christov", "christov2004"]:
        return _ecg_findpeaks_christov
    elif method in ["engzee", "engzee2012", "engzeemod", "engzeemod2012"]:
        return _ecg_findpeaks_engzee
    elif method in ["manikandan", "manikandan2012"]:
        return _ecg_findpeaks_manikandan
    elif method in ["elgendi", "elgendi2010"]:
        return _ecg_findpeaks_elgendi
    elif method in ["kalidas2017", "swt", "kalidas"]:
        return _ecg_findpeaks_kalidas
    elif method in ["martinez2004", "martinez"]:
        return _ecg_findpeaks_WT
    elif method in ["rodrigues2020", "rodrigues2021", "rodrigues", "asi"]:
        return _ecg_findpeaks_rodrigues
    elif method in ["vg", "vgraph", "koka2022"]:
        return _ecg_findpeaks_vgraph
    elif method in ["promac", "all"]:
        return _ecg_findpeaks_promac
    else:
        raise ValueError(
            f"NeuroKit error: ecg_findpeaks(): '{method}' not implemented."
        )


# =============================================================================
# Probabilistic Methods-Agreement via Convolution (ProMAC)
# =============================================================================
def _ecg_findpeaks_promac(
    signal,
    sampling_rate=1000,
    show=False,
    promac_methods=[
        "neurokit",
        "gamboa",
        "ssf",
        "zong",
        "engzee",
        "elgendi",
        "manikandan",
        "kalidas",
        "martinez",
        "rodrigues",
    ],
    threshold=0.33,
    gaussian_sd=100,
    **kwargs,
):
    """Probabilistic Methods-Agreement via Convolution (ProMAC).

    Parameters
    ----------
    signal : Union[list, np.array, pd.Series]
        The (cleaned) ECG channel, e.g. as returned by `ecg_clean()`.
    sampling_rate : int
        The sampling frequency of `ecg_signal` (in Hz, i.e., samples/second).
        Defaults to 1000.
    show : bool
        If True, will return a plot to visualizing the thresholds used in the algorithm.
        Useful for debugging.
    promac_methods : list of string
        The algorithms to be used for R-peak detection. See the list of acceptable algorithms for
        the 'ecg_peaks' function.
    threshold : float
        The tolerance for peak acceptance. This value is a percentage of the signal's maximum
        value. Only peaks found above this tolerance will be finally considered as actual peaks.
    gaussian_sd : int
        The standard deviation of the Gaussian distribution used to represent the peak location
        probability. This value should be in millisencods and is usually taken as the size of
        QRS complexes.

    """
    x = np.zeros(len(signal))
    promac_methods = [
        method.lower() for method in promac_methods
    ]  # remove capitalised letters
    error_list = []  # Stores the failed methods

    for method in promac_methods:
        try:
            func = _ecg_findpeaks_findmethod(method)
            x = _ecg_findpeaks_promac_addconvolve(
                signal, sampling_rate, x, func, gaussian_sd=gaussian_sd, **kwargs
            )
        except ValueError:
            error_list.append(f"Method '{method}' is not valid.")
        except Exception as error:
            error_list.append(f"{method} error: {error}")

    # Rescale
    x = x / np.max(x)
    convoluted = x.copy()

    # Remove below threshold
    x[x < threshold] = 0
    # Find peaks
    peaks = signal_findpeaks(x, height_min=threshold)["Peaks"]

    if show is True:
        signal_plot(
            pd.DataFrame({"ECG": signal, "Convoluted": convoluted}), standardize=True
        )
        [
            plt.axvline(x=peak, color="red", linestyle="--") for peak in peaks
        ]  # pylint: disable=W0106

    # I am not sure if mandatory print the best option
    if error_list:  # empty?
        print(error_list)

    return peaks


# _ecg_findpeaks_promac_addmethod + _ecg_findpeaks_promac_convolve
# Joining them makes parameters exposition more consistent
def _ecg_findpeaks_promac_addconvolve(
    signal, sampling_rate, x, fun, gaussian_sd=100, **kwargs
):
    peaks = fun(signal, sampling_rate=sampling_rate, **kwargs)

    mask = np.zeros(len(signal))
    mask[peaks] = 1

    # SD is defined as a typical QRS size, which for adults if 100ms
    sd = sampling_rate * gaussian_sd / 1000
    shape = scipy.stats.norm.pdf(
        np.linspace(-sd * 4, sd * 4, num=int(sd * 8)), loc=0, scale=sd
    )

    x += np.convolve(mask, shape, "same")

    return x


# =============================================================================
# NeuroKit
# =============================================================================
def _ecg_findpeaks_neurokit(
    signal,
    sampling_rate=1000,
    smoothwindow=0.1,
    avgwindow=0.75,
    gradthreshweight=1.5,
    minlenweight=0.4,
    mindelay=0.3,
    show=False,
):
    """All tune-able parameters are specified as keyword arguments.

    The `signal` must be the highpass-filtered raw ECG with a lowcut of .5 Hz.

    """
    if show is True:
        __, (ax1, ax2) = plt.subplots(nrows=2, ncols=1, sharex=True)

    # Compute the ECG's gradient as well as the gradient threshold. Run with
    # show=True in order to get an idea of the threshold.
    grad = np.gradient(signal)
    absgrad = np.abs(grad)
    smooth_kernel = int(np.rint(smoothwindow * sampling_rate))
    avg_kernel = int(np.rint(avgwindow * sampling_rate))
    smoothgrad = signal_smooth(absgrad, kernel="boxcar", size=smooth_kernel)
    avggrad = signal_smooth(smoothgrad, kernel="boxcar", size=avg_kernel)
    gradthreshold = gradthreshweight * avggrad
    mindelay = int(np.rint(sampling_rate * mindelay))

    if show is True:
        ax1.plot(signal)
        ax2.plot(smoothgrad)
        ax2.plot(gradthreshold)

    # Identify start and end of QRS complexes.
    qrs = smoothgrad > gradthreshold
    beg_qrs = np.where(np.logical_and(np.logical_not(qrs[0:-1]), qrs[1:]))[0]
    end_qrs = np.where(np.logical_and(qrs[0:-1], np.logical_not(qrs[1:])))[0]
    # Throw out QRS-ends that precede first QRS-start.
    end_qrs = end_qrs[end_qrs > beg_qrs[0]]

    # Identify R-peaks within QRS (ignore QRS that are too short).
    num_qrs = min(beg_qrs.size, end_qrs.size)
    min_len = np.mean(end_qrs[:num_qrs] - beg_qrs[:num_qrs]) * minlenweight
    peaks = [0]

    for i in range(num_qrs):
        beg = beg_qrs[i]
        end = end_qrs[i]
        len_qrs = end - beg

        if len_qrs < min_len:
            continue

        if show is True:
            ax2.axvspan(beg, end, facecolor="m", alpha=0.5)

        # Find local maxima and their prominence within QRS.
        data = signal[beg:end]
        locmax, props = scipy.signal.find_peaks(data, prominence=(None, None))

        if locmax.size > 0:
            # Identify most prominent local maximum.
            peak = beg + locmax[np.argmax(props["prominences"])]
            # Enforce minimum delay between peaks.
            if peak - peaks[-1] > mindelay:
                peaks.append(peak)

    peaks.pop(0)

    if show is True:
        ax1.scatter(peaks, signal[peaks], c="r")

    peaks = np.asarray(peaks).astype(int)  # Convert to int
    return peaks


# =============================================================================
# Pan & Tompkins (1985)
# =============================================================================
def _ecg_findpeaks_pantompkins(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Pan, J., & Tompkins, W. J. (1985). A real-time QRS detection algorithm. IEEE transactions
      on biomedical engineering, (3), 230-236.

    """
    diff = np.diff(signal)

    squared = diff * diff

    N = int(0.12 * sampling_rate)
    mwa = _ecg_findpeaks_MWA(squared, N)
    mwa[: int(0.2 * sampling_rate)] = 0

    mwa_peaks = _ecg_findpeaks_peakdetect(mwa, sampling_rate)

    mwa_peaks = np.array(mwa_peaks, dtype="int")
    return mwa_peaks


# =============================================================================
# Hamilton (2002)
# =============================================================================
def _ecg_findpeaks_hamilton(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Hamilton, Open Source ECG Analysis Software Documentation, E.P.Limited, 2002.

    """
    diff = abs(np.diff(signal))

    b = np.ones(int(0.08 * sampling_rate))
    b = b / int(0.08 * sampling_rate)
    a = [1]

    ma = scipy.signal.lfilter(b, a, diff)

    ma[0 : len(b) * 2] = 0

    n_pks = []
    n_pks_ave = 0.0
    s_pks = []
    s_pks_ave = 0.0
    QRS = [0]
    RR = []
    RR_ave = 0.0

    th = 0.0

    i = 0
    idx = []
    peaks = []

    for i in range(len(ma)):  # pylint: disable=C0200,R1702
        if (
            i > 0 and i < len(ma) - 1 and ma[i - 1] < ma[i] and ma[i + 1] < ma[i]
        ):  # pylint: disable=R1716
            peak = i
            peaks.append(peak)
            if ma[peak] > th and (peak - QRS[-1]) > 0.3 * sampling_rate:
                QRS.append(peak)
                idx.append(peak)
                s_pks.append(ma[peak])
                if len(n_pks) > 8:
                    s_pks.pop(0)
                s_pks_ave = np.mean(s_pks)

                if RR_ave != 0.0 and QRS[-1] - QRS[-2] > 1.5 * RR_ave:
                    missed_peaks = peaks[idx[-2] + 1 : idx[-1]]
                    for missed_peak in missed_peaks:
                        if (
                            missed_peak - peaks[idx[-2]] > int(0.36 * sampling_rate)
                            and ma[missed_peak] > 0.5 * th
                        ):
                            QRS.append(missed_peak)
                            QRS.sort()
                            break

                if len(QRS) > 2:
                    RR.append(QRS[-1] - QRS[-2])
                    if len(RR) > 8:
                        RR.pop(0)
                    RR_ave = int(np.mean(RR))

            else:
                n_pks.append(ma[peak])
                if len(n_pks) > 8:
                    n_pks.pop(0)
                n_pks_ave = np.mean(n_pks)

            th = n_pks_ave + 0.45 * (s_pks_ave - n_pks_ave)

            i += 1

    QRS.pop(0)

    QRS = np.array(QRS, dtype="int")
    return QRS


# =============================================================================
# Slope Sum Function (SSF) - Zong et al. (2003)
# =============================================================================
def _ecg_findpeaks_ssf(
    signal, sampling_rate=1000, threshold=20, before=0.03, after=0.01, **kwargs
):
    """From https://github.com/PIA-
    Group/BioSPPy/blob/e65da30f6379852ecb98f8e2e0c9b4b5175416c3/biosppy/signals/ecg.py#L448.

    """
    # TODO: Doesn't really seems to work

    # convert to samples
    winB = int(before * sampling_rate)
    winA = int(after * sampling_rate)

    Rset = set()
    length = len(signal)

    # diff
    dx = np.diff(signal)
    dx[dx >= 0] = 0
    dx = dx**2

    # detection
    (idx,) = np.nonzero(dx > threshold)
    idx0 = np.hstack(([0], idx))
    didx = np.diff(idx0)

    # search
    sidx = idx[didx > 1]
    for item in sidx:
        a = item - winB
        if a < 0:
            a = 0
        b = item + winA
        if b > length:
            continue

        r = np.argmax(signal[a:b]) + a
        Rset.add(r)

    # output
    rpeaks = list(Rset)
    rpeaks.sort()
    rpeaks = np.array(rpeaks, dtype="int")
    return rpeaks


# =============================================================================
# Zong (2003) - WQRS
# =============================================================================
def _ecg_findpeaks_zong(signal, sampling_rate=1000, cutoff=16, window=0.13, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Zong, W., Moody, G. B., & Jiang, D. (2003, September). A robust open-source algorithm to
      detect onset and duration of QRS complexes. In Computers in Cardiology, 2003 (pp. 737-740).
      IEEE.
    """

    # 1. Filter signal
    # TODO: Should remove this step? It's technically part of cleaning,
    # Not sure it is integral to the peak-detection per se. Opinions are welcome.
    order = 2
    # Cutoff normalized by nyquist frequency
    b, a = scipy.signal.butter(order, cutoff / (0.5 * sampling_rate))
    y = scipy.signal.lfilter(b, a, signal)

    # Curve length transformation
    w = int(np.ceil(window * sampling_rate))
    tmp = np.zeros(len(y) - w)
    for i, j in enumerate(np.arange(w, len(y))):
        s = y[j - w : j]
        tmp[i] = np.sum(
            np.sqrt(
                np.power(1 / sampling_rate, 2) * np.ones(w - 1)
                + np.power(np.diff(s), 2)
            )
        )
    # Pad with the first value
    clt = np.concatenate([[tmp[0]] * w, tmp])

    # Find adaptive threshold
    window_size = 10 * sampling_rate

    # Apply fast moving window average with 1D convolution

    ret = np.pad(clt, (window_size - 1, 0), "constant", constant_values=(0, 0))
    ret = np.convolve(ret, np.ones(window_size), "valid")

    for i in range(1, window_size):
        ret[i - 1] = ret[i - 1] / i
    ret[window_size - 1 :] = ret[window_size - 1 :] / window_size

    # Find peaks
    peaks = []
    for i in range(len(clt)):
        z = sampling_rate * 0.35
        if (len(peaks) == 0 or i > peaks[-1] + z) and clt[i] > ret[i]:
            peaks.append(i)

    return np.array(peaks)


# =============================================================================
# Christov (2004)
# =============================================================================
def _ecg_findpeaks_christov(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Ivaylo I. Christov, Real time electrocardiogram QRS detection using combined adaptive
      threshold, BioMedical Engineering OnLine 2004, vol. 3:28, 2004.

    """
    total_taps = 0

    b = np.ones(int(0.02 * sampling_rate))
    b = b / int(0.02 * sampling_rate)
    total_taps += len(b)
    a = [1]

    MA1 = scipy.signal.lfilter(b, a, signal)

    b = np.ones(int(0.028 * sampling_rate))
    b = b / int(0.028 * sampling_rate)
    total_taps += len(b)
    a = [1]

    MA2 = scipy.signal.lfilter(b, a, MA1)

    Y = []
    for i in range(1, len(MA2) - 1):
        diff = abs(MA2[i + 1] - MA2[i - 1])

        Y.append(diff)

    b = np.ones(int(0.040 * sampling_rate))
    b = b / int(0.040 * sampling_rate)
    total_taps += len(b)
    a = [1]

    MA3 = scipy.signal.lfilter(b, a, Y)

    MA3[0:total_taps] = 0

    ms50 = int(0.05 * sampling_rate)
    ms200 = int(0.2 * sampling_rate)
    ms1200 = int(1.2 * sampling_rate)
    ms350 = int(0.35 * sampling_rate)

    M = 0
    newM5 = 0
    M_list = []
    MM = []
    M_slope = np.linspace(1.0, 0.6, ms1200 - ms200)
    F = 0
    F_list = []
    R = 0
    RR = []
    Rm = 0
    R_list = []

    MFR = 0
    MFR_list = []

    QRS = []

    for i in range(len(MA3)):  # pylint: disable=C0200
        # M
        if i < 5 * sampling_rate:
            M = 0.6 * np.max(MA3[: i + 1])
            MM.append(M)
            if len(MM) > 5:
                MM.pop(0)

        elif QRS and i < QRS[-1] + ms200:
            newM5 = 0.6 * np.max(MA3[QRS[-1] : i])
            if newM5 > 1.5 * MM[-1]:
                newM5 = 1.1 * MM[-1]

        elif QRS and i == QRS[-1] + ms200:
            if newM5 == 0:
                newM5 = MM[-1]
            MM.append(newM5)
            if len(MM) > 5:
                MM.pop(0)
            M = np.mean(MM)

        elif QRS and i > QRS[-1] + ms200 and i < QRS[-1] + ms1200:
            M = np.mean(MM) * M_slope[i - (QRS[-1] + ms200)]

        elif QRS and i > QRS[-1] + ms1200:
            M = 0.6 * np.mean(MM)

        # F
        if i > ms350:
            F_section = MA3[i - ms350 : i]
            max_latest = np.max(F_section[-ms50:])
            max_earliest = np.max(F_section[:ms50])
            F += (max_latest - max_earliest) / 150.0

        # R
        if QRS and i < QRS[-1] + int((2.0 / 3.0 * Rm)):
            R = 0

        elif QRS and i > QRS[-1] + int((2.0 / 3.0 * Rm)) and i < QRS[-1] + Rm:
            dec = (M - np.mean(MM)) / 1.4
            R = 0 + dec

        MFR = M + F + R
        M_list.append(M)
        F_list.append(F)
        R_list.append(R)
        MFR_list.append(MFR)

        if not QRS and MA3[i] > MFR:
            QRS.append(i)

        elif QRS and i > QRS[-1] + ms200 and MA3[i] > MFR:
            QRS.append(i)
            if len(QRS) > 2:
                RR.append(QRS[-1] - QRS[-2])
                if len(RR) > 5:
                    RR.pop(0)
                Rm = int(np.mean(RR))

    QRS.pop(0)
    QRS = np.array(QRS, dtype="int")
    return QRS


# =============================================================================
# Continuous Wavelet Transform (CWT) - Martinez et al. (2004)
# =============================================================================
def _ecg_findpeaks_WT(signal, sampling_rate=1000, **kwargs):
    # Try loading pywt
    try:
        import pywt
    except ImportError as import_error:
        raise ImportError(
            "NeuroKit error: ecg_delineator(): the 'PyWavelets' module is required for"
            " this method to run. Please install it first (`pip install PyWavelets`)."
        ) from import_error
    # first derivative of the Gaissian signal
    scales = np.array([1, 2, 4, 8, 16])
    cwtmatr, __ = pywt.cwt(signal, scales, "gaus1", sampling_period=1.0 / sampling_rate)

    # For wt of scale 2^4
    signal_4 = cwtmatr[4, :]
    epsilon_4 = np.sqrt(np.mean(np.square(signal_4)))
    peaks_4, _ = scipy.signal.find_peaks(np.abs(signal_4), height=epsilon_4)

    # For wt of scale 2^3
    signal_3 = cwtmatr[3, :]
    epsilon_3 = np.sqrt(np.mean(np.square(signal_3)))
    peaks_3, _ = scipy.signal.find_peaks(np.abs(signal_3), height=epsilon_3)
    # Keep only peaks_3 that are nearest to peaks_4
    peaks_3_keep = np.zeros_like(peaks_4)
    for i in range(len(peaks_4)):  # pylint: disable=C0200
        peaks_distance = abs(peaks_4[i] - peaks_3)
        peaks_3_keep[i] = peaks_3[np.argmin(peaks_distance)]

    # For wt of scale 2^2
    signal_2 = cwtmatr[2, :]
    epsilon_2 = np.sqrt(np.mean(np.square(signal_2)))
    peaks_2, _ = scipy.signal.find_peaks(np.abs(signal_2), height=epsilon_2)
    # Keep only peaks_2 that are nearest to peaks_3
    peaks_2_keep = np.zeros_like(peaks_4)
    for i in range(len(peaks_4)):
        peaks_distance = abs(peaks_3_keep[i] - peaks_2)
        peaks_2_keep[i] = peaks_2[np.argmin(peaks_distance)]

    # For wt of scale 2^1
    signal_1 = cwtmatr[1, :]
    epsilon_1 = np.sqrt(np.mean(np.square(signal_1)))
    peaks_1, _ = scipy.signal.find_peaks(np.abs(signal_1), height=epsilon_1)
    # Keep only peaks_1 that are nearest to peaks_2
    peaks_1_keep = np.zeros_like(peaks_4)
    for i in range(len(peaks_4)):
        peaks_distance = abs(peaks_2_keep[i] - peaks_1)
        peaks_1_keep[i] = peaks_1[np.argmin(peaks_distance)]

    # Find R peaks
    max_R_peak_dist = int(0.1 * sampling_rate)
    rpeaks = []
    for index_cur, index_next in zip(peaks_1_keep[:-1], peaks_1_keep[1:]):
        correct_sign = (
            signal_1[index_cur] < 0 and signal_1[index_next] > 0
        )  # pylint: disable=R1716
        near = (index_next - index_cur) < max_R_peak_dist  # limit 2
        if near and correct_sign:
            rpeaks.append(
                signal_zerocrossings(signal_1[index_cur : index_next + 1])[0]
                + index_cur
            )

    rpeaks = np.array(rpeaks, dtype="int")
    return rpeaks


# =============================================================================
# Gamboa (2008)
# =============================================================================
def _ecg_findpeaks_gamboa(signal, sampling_rate=1000, tol=0.002, **kwargs):
    """From https://github.com/PIA-
    Group/BioSPPy/blob/e65da30f6379852ecb98f8e2e0c9b4b5175416c3/biosppy/signals/ecg.py#L834.

    - Gamboa, H. (2008). Multi-modal behavioral biometrics based on HCI and electrophysiology
      (Doctoral dissertation, Universidade Técnica de Lisboa).

    """

    hist, edges = np.histogram(signal, 100, density=True)

    TH = 0.01
    F = np.cumsum(hist)

    v0 = edges[np.nonzero(F > TH)[0][0]]
    v1 = edges[np.nonzero(F < (1 - TH))[0][-1]]

    nrm = max([abs(v0), abs(v1)])
    norm_signal = signal / float(nrm)

    d2 = np.diff(norm_signal, 2)

    b = (
        np.nonzero((np.diff(np.sign(np.diff(-d2)))) == -2)[0] + 2
    )  # pylint: disable=E1130
    b = np.intersect1d(b, np.nonzero(-d2 > tol)[0])  # pylint: disable=E1130

    rpeaks = []
    if len(b) >= 3:
        b = b.astype("float")
        previous = b[0]
        # convert to samples
        v_100ms = int(0.1 * sampling_rate)
        v_300ms = int(0.3 * sampling_rate)
        for i in b[1:]:
            if i - previous > v_300ms:
                previous = i
                rpeaks.append(np.argmax(signal[int(i) : int(i + v_100ms)]) + i)

    rpeaks = sorted(list(set(rpeaks)))
    rpeaks = np.array(rpeaks, dtype="int")
    return rpeaks


# =============================================================================
# Elgendi et al. (2010)
# =============================================================================
def _ecg_findpeaks_elgendi(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Elgendi, Mohamed & Jonkman, Mirjam & De Boer, Friso. (2010). Frequency Bands Effects on QRS
      Detection. The 3rd International Conference on Bio-inspired Systems and Signal Processing
      (BIOSIGNALS2010). 428-431.

    """

    window1 = int(0.12 * sampling_rate)
    mwa_qrs = _ecg_findpeaks_MWA(abs(signal), window1)

    window2 = int(0.6 * sampling_rate)
    mwa_beat = _ecg_findpeaks_MWA(abs(signal), window2)

    blocks = np.zeros(len(signal))
    block_height = np.max(signal)

    for i in range(len(mwa_qrs)):  # pylint: disable=C0200
        blocks[i] = block_height if mwa_qrs[i] > mwa_beat[i] else 0
    QRS = []

    for i in range(1, len(blocks)):
        if blocks[i - 1] == 0 and blocks[i] == block_height:
            start = i

        elif blocks[i - 1] == block_height and blocks[i] == 0:
            end = i - 1

            if end - start > int(0.08 * sampling_rate):
                detection = np.argmax(signal[start : end + 1]) + start
                if QRS:
                    if detection - QRS[-1] > int(0.3 * sampling_rate):
                        QRS.append(detection)
                else:
                    QRS.append(detection)

    QRS = np.array(QRS, dtype="int")
    return QRS


# =============================================================================
# Engzee Modified (2012)
# =============================================================================
def _ecg_findpeaks_engzee(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - C. Zeelenberg, A single scan algorithm for QRS detection and feature extraction, IEEE Comp.
      in Cardiology, vol. 6, pp. 37-42, 1979
    - A. Lourenco, H. Silva, P. Leite, R. Lourenco and A. Fred, "Real Time Electrocardiogram
      Segmentation for Finger Based ECG Biometrics", BIOSIGNALS 2012, pp. 49-54, 2012.

    """
    engzee_fake_delay = 0

    diff = np.zeros(len(signal))
    for i in range(4, len(diff)):
        diff[i] = signal[i] - signal[i - 4]

    ci = [1, 4, 6, 4, 1]
    low_pass = scipy.signal.lfilter(ci, 1, diff)

    low_pass[: int(0.2 * sampling_rate)] = 0

    ms200 = int(0.2 * sampling_rate)
    ms1200 = int(1.2 * sampling_rate)
    ms160 = int(0.16 * sampling_rate)
    neg_threshold = int(0.01 * sampling_rate)

    M = 0
    M_list = []
    neg_m = []
    MM = []
    M_slope = np.linspace(1.0, 0.6, ms1200 - ms200)

    QRS = []
    r_peaks = []

    counter = 0

    thi_list = []
    thi = False
    thf_list = []
    thf = False
    newM5 = False

    for i in range(len(low_pass)):  # pylint: disable=C0200
        # M
        if i < 5 * sampling_rate:
            M = 0.6 * np.max(low_pass[: i + 1])
            MM.append(M)
            if len(MM) > 5:
                MM.pop(0)

        elif QRS and i < QRS[-1] + ms200:
            newM5 = 0.6 * np.max(low_pass[QRS[-1] : i])

            if newM5 > 1.5 * MM[-1]:
                newM5 = 1.1 * MM[-1]

        elif newM5 and QRS and i == QRS[-1] + ms200:
            MM.append(newM5)
            if len(MM) > 5:
                MM.pop(0)
            M = np.mean(MM)

        elif QRS and i > QRS[-1] + ms200 and i < QRS[-1] + ms1200:
            M = np.mean(MM) * M_slope[i - (QRS[-1] + ms200)]

        elif QRS and i > QRS[-1] + ms1200:
            M = 0.6 * np.mean(MM)

        M_list.append(M)
        neg_m.append(-M)

        if not QRS and low_pass[i] > M:
            QRS.append(i)
            thi_list.append(i)
            thi = True

        elif QRS and i > QRS[-1] + ms200 and low_pass[i] > M:
            QRS.append(i)
            thi_list.append(i)
            thi = True

        if thi and i < thi_list[-1] + ms160:
            if low_pass[i] < -M and low_pass[i - 1] > -M:
                # thf_list.append(i)
                thf = True

            if thf and low_pass[i] < -M:
                thf_list.append(i)
                counter += 1

            elif low_pass[i] > -M and thf:
                counter = 0
                thi = False
                thf = False

        elif thi and i > thi_list[-1] + ms160:
            counter = 0
            thi = False
            thf = False

        if counter > neg_threshold:
            unfiltered_section = signal[thi_list[-1] - int(0.01 * sampling_rate) : i]
            r_peaks.append(
                engzee_fake_delay
                + np.argmax(unfiltered_section)
                + thi_list[-1]
                - int(0.01 * sampling_rate)
            )
            counter = 0
            thi = False
            thf = False

    r_peaks.pop(
        0
    )  # removing the 1st detection as it 1st needs the QRS complex amplitude for the threshold
    r_peaks = np.array(r_peaks, dtype="int")
    return r_peaks


# =============================================================================
# Shannon energy R-peak detection - Manikandan and Soman (2012)
# =============================================================================
def _ecg_findpeaks_manikandan(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/hongzuL/A-novel-method-for-detecting-R-peaks-in-electrocardiogram-signal/

    A (hopefully) fixed version of https://github.com/nsunami/Shannon-Energy-R-Peak-Detection
    """

    # Preprocessing ------------------------------------------------------------
    # Forward and backward filtering using filtfilt.
    def cheby1_bandpass_filter(data, lowcut, highcut, fs, order=5, rp=1):
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = scipy.signal.cheby1(order, rp=rp, Wn=[low, high], btype="bandpass")
        y = scipy.signal.filtfilt(b, a, data)
        return y

    # Running mean filter function
    def running_mean(x, N):
        cumsum = np.cumsum(np.insert(x, 0, 0))
        return (cumsum[N:] - cumsum[:-N]) / float(N)

    # Apply Chebyshev Type I Bandpass filter
    # Low cut frequency = 6 Hz
    # High cut frequency = 18
    filtered = cheby1_bandpass_filter(
        signal, lowcut=6, highcut=18, fs=sampling_rate, order=4
    )

    # Eq. 1: First-order differencing difference
    dn = np.append(filtered[1:], 0) - filtered
    # Eq. 2
    dtn = dn / (np.max(abs(dn)))

    # The absolute value, energy value, Shannon entropy value, and Shannon energy value
    # # Eq. 3
    # an = np.abs(dtn)
    # # Eq. 4
    # en = an**2
    # # Eq. 5
    # sen = -np.abs(dtn) * np.log10(np.abs(dtn))
    # Eq. 6
    sn = -(dtn**2) * np.log10(dtn**2)

    # Apply rectangular window
    # Length should be approximately the same as the duration of possible wider QRS complex
    # Normal QRS duration is .12 sec, so we overshoot with 0.15 sec
    window_len = int(0.15 * sampling_rate)
    window_len = window_len - 1 if window_len % 2 == 0 else window_len  # Make odd
    window = scipy.signal.windows.boxcar(window_len)

    # The filtering operation is performed in both the forward and reverse directions
    see = scipy.signal.convolve(sn, window, mode="same")
    see = np.flip(see)
    see = scipy.signal.convolve(see, window, "same")
    see = np.flip(see)

    # Hilbert Transformation
    ht = np.imag(scipy.signal.hilbert(see))

    # Moving Average to remove low frequency drift
    # 2.5 sec from Manikanda in 360 Hz (900 samples)
    # 2.5 sec in 500 Hz == 1250 samples
    ma_len = int(2.5 * sampling_rate)
    ma_out = np.insert(running_mean(ht, ma_len), 0, [0] * (ma_len - 1))

    # Get the difference between the Hilbert signal and the MA filtered signal
    zn = ht - ma_out

    # R-Peak Detection ---------------------------------------------------------
    # Look for points crossing zero

    # Find points crossing zero upwards (negative to positive)
    idx = np.argwhere(np.diff(np.sign(zn)) > 0).flatten().tolist()
    # Prepare a container for windows
    idx_search = []
    id_maxes = np.empty(0, dtype=int)
    search_window_half = int(np.ceil(window_len / 2))
    for i in idx:
        lows = np.arange(i - search_window_half, i)
        highs = np.arange(i + 1, i + search_window_half + 1)
        if highs[-1] > len(signal):
            highs = np.delete(
                highs, np.arange(np.where(highs == len(signal))[0], len(highs) + 1)
            )
        ekg_window = np.concatenate((lows, [i], highs))
        idx_search.append(ekg_window)
        ekg_window_wave = signal[ekg_window]
        id_maxes = np.append(
            id_maxes,
            ekg_window[np.where(ekg_window_wave == np.max(ekg_window_wave))[0]],
        )
    return np.array(idx)


# =============================================================================
# Stationary Wavelet Transform  (SWT) - Kalidas and Tamil (2017)
# =============================================================================
def _ecg_findpeaks_kalidas(signal, sampling_rate=1000, **kwargs):
    """From https://github.com/berndporr/py-ecg-detectors/

    - Vignesh Kalidas and Lakshman Tamil (2017). Real-time QRS detector using Stationary Wavelet Transform
      for Automated ECG Analysis. In: 2017 IEEE 17th International Conference on Bioinformatics and
      Bioengineering (BIBE). Uses the Pan and Tompkins thresolding.

    """
    # Try loading pywt
    try:
        import pywt
    except ImportError as import_error:
        raise ImportError(
            "NeuroKit error: ecg_findpeaks(): the 'PyWavelets' module is required for"
            " this method to run. Please install it first (`pip install PyWavelets`)."
        ) from import_error

    signal_length = len(signal)

    swt_level = 3
    padding = -1
    for i in range(1000):
        if (len(signal) + i) % 2**swt_level == 0:
            padding = i
            break

    if padding > 0:
        signal = np.pad(signal, (0, padding), "edge")
    elif padding == -1:
        print("Padding greater than 1000 required\n")

    swt_ecg = pywt.swt(signal, "db3", level=swt_level)
    swt_ecg = np.array(swt_ecg)
    swt_ecg = swt_ecg[0, 1, :]

    squared = swt_ecg * swt_ecg

    f1 = 0.01 / (0.5 * sampling_rate)
    f2 = 10 / (0.5 * sampling_rate)

    sos = scipy.signal.butter(3, [f1, f2], btype="bandpass", output="sos")
    filtered_squared = scipy.signal.sosfilt(sos, squared)

    # Drop padding to avoid detecting peaks inside it (#456)
    filtered_squared = filtered_squared[:signal_length]

    filt_peaks = _ecg_findpeaks_peakdetect(filtered_squared, sampling_rate)

    filt_peaks = np.array(filt_peaks, dtype="int")
    return filt_peaks


# ===========================================================================
# Nabian et al. (2018)
# ===========================================================================
def _ecg_findpeaks_nabian2018(signal, sampling_rate=1000, **kwargs):
    """R peak detection method by Nabian et al. (2018) inspired by the Pan-Tompkins algorithm.

    - Nabian, M., Yin, Y., Wormwood, J., Quigley, K. S., Barrett, L. F., Ostadabbas, S. (2018).
      An Open-Source Feature Extraction Tool for the Analysis of Peripheral Physiological Data.
      IEEE Journal of Translational Engineering in Health and Medicine, 6, 1-11.

    """
    window_size = int(0.4 * sampling_rate)

    peaks = np.zeros(len(signal))

    for i in range(1 + window_size, len(signal) - window_size):
        ecg_window = signal[i - window_size : i + window_size]
        rpeak = np.argmax(ecg_window)

        if i == (i - window_size - 1 + rpeak):
            peaks[i] = 1

    rpeaks = np.where(peaks == 1)[0]

    # min_distance = 200

    return rpeaks


# =============================================================================
# ASI (FSM based 2020)
# =============================================================================


def _ecg_findpeaks_rodrigues(signal, sampling_rate=1000, **kwargs):
    """Segmenter by Tiago Rodrigues, inspired by on Gutierrez-Rivas (2015) and Sadhukhan (2012).

    References
    ----------
    - Gutiérrez-Rivas, R., García, J. J., Marnane, W. P., & Hernández, A. (2015). Novel real-time
      low-complexity QRS complex detector based on adaptive thresholding. IEEE Sensors Journal,
      15(10), 6036-6043.

    - Sadhukhan, D., & Mitra, M. (2012). R-peak detection algorithm for ECG using double difference
      and RR interval processing. Procedia Technology, 4, 873-877.

    """

    N = int(np.clip(np.round(3 * sampling_rate / 128), 2, None))
    Nd = N - 1
    Pth = (0.7 * sampling_rate) / 128 + 2.7
    # Pth = 3, optimal for fs = 250 Hz
    Rmin = 0.26

    rpeaks = []
    i = 1
    Ramptotal = 0

    # Double derivative squared
    diff_ecg = [signal[i] - signal[i - Nd] for i in range(Nd, len(signal))]
    ddiff_ecg = [diff_ecg[i] - diff_ecg[i - 1] for i in range(1, len(diff_ecg))]
    squar = np.square(ddiff_ecg)

    # Integrate moving window
    b = np.array(np.ones(N))
    a = [1]
    processed_ecg = scipy.signal.lfilter(b, a, squar)
    tf = len(processed_ecg)
    rpeakpos = 0
    # R-peak finder FSM
    while i < tf:  # ignore last sample of recording
        # State 1: looking for maximum
        tf1 = np.round(i + Rmin * sampling_rate)
        Rpeakamp = 0
        while i < tf1 and i < tf:
            # Rpeak amplitude and position
            if processed_ecg[i] > Rpeakamp:
                Rpeakamp = processed_ecg[i]
                rpeakpos = i + 1
            i += 1

        Ramptotal = (19 / 20) * Ramptotal + (1 / 20) * Rpeakamp
        rpeaks.append(rpeakpos)

        # State 2: waiting state
        d = tf1 - rpeakpos
        tf2 = i + np.round(0.2 * 2 - d)
        while i <= tf2:
            i += 1

        # State 3: decreasing threshold
        Thr = Ramptotal
        while i < tf and processed_ecg[i] < Thr:
            Thr *= np.exp(-Pth / sampling_rate)
            i += 1

    rpeaks = np.array(rpeaks, dtype="int")
    return rpeaks


# =============================================================================
# Visibility graph transformation - by Koka and Muma (2022)
# =============================================================================
def _ecg_findpeaks_vgraph(signal, sampling_rate=1000, lowcut=3, order=2, **kwargs):
    """R-Peak Detector Using Visibility Graphs by Taulant Koka and Michael Muma (2022).

    References
    ----------
    - T. Koka and M. Muma (2022), Fast and Sample Accurate R-Peak Detection for Noisy ECG Using
      Visibility Graphs. In: 2022 44th Annual International Conference of the IEEE Engineering
      in Medicine & Biology Society (EMBC). Uses the Pan and Tompkins thresholding.

    """
    # Try loading ts2vg
    try:
        import ts2vg
    except ImportError as import_error:
        raise ImportError(
            "NeuroKit error: ecg_findpeaks(): the 'ts2vg' module is required for"
            " this method to run. Please install it first (`pip install ts2vg`)."
        ) from import_error

    N = len(signal)
    M = 2 * sampling_rate
    w = np.zeros(N)
    rpeaks = []
    beta = 0.55
    gamma = 0.5
    L = 0
    R = M

    # Compute number of segments
    deltaM = int(gamma * M)
    n_segments = int((N - deltaM) / (M - deltaM)) + 1

    for segment in range(n_segments):
        y = signal[L:R]

        # Compute the adjacency matrix to the directed visibility graph
        A = ts2vg.NaturalVG(directed="top_to_bottom").build(y).adjacency_matrix()
        _w = np.ones(len(y))

        # Computee the weights for the ecg using its VG transformation
        while np.count_nonzero(_w) / len(y) >= beta:
            _w = np.matmul(A, _w) / np.linalg.norm(_w)

        # Update the weight vector
        if L == 0:
            w[L:R] = _w
        elif N - deltaM <= L < L < N:
            w[L:] = 0.5 * (_w + w[L:])
        else:
            w[L : L + deltaM] = 0.5 * (_w[:deltaM] + w[L : L + deltaM])
            w[L + deltaM : R] = _w[deltaM:]

        # Update the boundary conditions
        L = L + (M - deltaM)
        if R + (M - deltaM) <= N:
            R = R + (M - deltaM)
        else:
            R = N

        # Multiply signal by its weights and apply thresholding algorithm
        weighted_signal = signal * w
        rpeaks = _ecg_findpeaks_peakdetect(weighted_signal, sampling_rate)
        rpeaks = np.array(rpeaks, dtype="int")
    return rpeaks


# =============================================================================
# Utilities
# =============================================================================


def _ecg_findpeaks_MWA(signal, window_size, **kwargs):
    """Based on https://github.com/berndporr/py-ecg-detectors/

    Optimized for vectorized computation.

    """

    window_size = int(window_size)

    # Scipy's uniform_filter1d is a fast and accurate way of computing
    # moving averages. By default it computes the averages of `window_size`
    # elements centered around each element in the input array, including
    # `(window_size - 1) // 2` elements after the current element (when
    # `window_size` is even, the extra element is taken from before). To
    # return causal moving averages, i.e. each output element is the average
    # of window_size input elements ending at that position, we use the
    # `origin` argument to shift the filter computation accordingly.
    mwa = scipy.ndimage.uniform_filter1d(
        signal, window_size, origin=(window_size - 1) // 2
    )

    # Compute actual moving averages for the first `window_size - 1` elements,
    # which the uniform_filter1d function computes using padding. We want
    # those output elements to be averages of only the input elements until
    # that position.
    head_size = min(window_size - 1, len(signal))
    mwa[:head_size] = np.cumsum(signal[:head_size]) / np.linspace(
        1, head_size, head_size
    )

    return mwa


def _ecg_findpeaks_peakdetect(detection, sampling_rate=1000, **kwargs):
    """Based on https://github.com/berndporr/py-ecg-detectors/

    Optimized for vectorized computation.

    """
    min_peak_distance = int(0.3 * sampling_rate)
    min_missed_distance = int(0.25 * sampling_rate)

    signal_peaks = []

    SPKI = 0.0
    NPKI = 0.0

    last_peak = 0
    last_index = -1

    # NOTE: Using plateau_size=(1,1) here avoids detecting flat peaks and
    # maintains original py-ecg-detectors behaviour. Flat peaks are typically
    # found in measurement artifacts where the signal saturates at maximum
    # recording amplitude. Such cases should not be detected as peaks. If we
    # do encounter recordings where even normal R peaks are flat, then changing
    # this to something like plateau_size=(1, sampling_rate // 10) might make
    # sense. See also https://github.com/neuropsychology/NeuroKit/pull/450.
    peaks, _ = scipy.signal.find_peaks(detection, plateau_size=(1, 1))
    for index, peak in enumerate(peaks):
        peak_value = detection[peak]

        threshold_I1 = NPKI + 0.25 * (SPKI - NPKI)
        if peak_value > threshold_I1 and peak > last_peak + min_peak_distance:
            signal_peaks.append(peak)

            # RR_missed threshold is based on the previous eight R-R intervals
            if len(signal_peaks) > 9:
                RR_ave = (signal_peaks[-2] - signal_peaks[-10]) // 8
                RR_missed = int(1.66 * RR_ave)
                if peak - last_peak > RR_missed:
                    missed_peaks = peaks[last_index + 1 : index]
                    missed_peaks = missed_peaks[
                        (missed_peaks > last_peak + min_missed_distance)
                        & (missed_peaks < peak - min_missed_distance)
                    ]
                    threshold_I2 = 0.5 * threshold_I1
                    missed_peaks = missed_peaks[detection[missed_peaks] > threshold_I2]
                    if len(missed_peaks) > 0:
                        signal_peaks[-1] = missed_peaks[
                            np.argmax(detection[missed_peaks])
                        ]
                        signal_peaks.append(peak)

            last_peak = peak
            last_index = index

            SPKI = 0.125 * peak_value + 0.875 * SPKI
        else:
            NPKI = 0.125 * peak_value + 0.875 * NPKI

    return signal_peaks
