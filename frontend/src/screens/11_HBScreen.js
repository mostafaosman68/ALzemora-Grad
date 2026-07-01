import React, {useCallback, useMemo, useState, useRef, useEffect} from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Platform,
  ActivityIndicator,
  RefreshControl,
  Animated,
  Easing,
} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {ScreenBg, TopBar, DarkBtn, BackBtn, COLORS, SectionTitle} from '../components/UI';
import {useAuth} from '../../App';
import {fetchLiveHeartbeat} from '../services/heartbeatService';
import {requestBlePermissions, startHeartRateMonitor} from '../services/bleHeartRateService';

const POLL_INTERVAL_MS = 3000;

function formatLastSeen(lastSeenAt, secondsAgo) {
  if (!lastSeenAt) {
    return 'No readings yet';
  }
  const date = new Date(lastSeenAt);
  if (Number.isNaN(date.getTime())) {
    return 'No readings yet';
  }
  const seenTime = date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  return typeof secondsAgo === 'number' ? `${seenTime} • ${secondsAgo}s ago` : seenTime;
}

function HeartPulse({active, bpm}) {
  const heartScale = useRef(new Animated.Value(1)).current;
  const ringScale  = useRef(new Animated.Value(1)).current;
  const ringOpacity = useRef(new Animated.Value(0)).current;
  const animRef = useRef(null);

  useEffect(() => {
    if (animRef.current) {
      animRef.current.stop();
      animRef.current = null;
    }

    if (!active) {
      heartScale.setValue(1);
      ringScale.setValue(1);
      ringOpacity.setValue(0);
      return;
    }

    // Beat interval from live BPM; clamp to a sensible range
    const safeBpm = bpm && bpm > 20 && bpm < 220 ? bpm : 70;
    const beatMs = (60 / safeBpm) * 1000;
    const contractMs = beatMs * 0.25;
    const expandMs   = beatMs * 0.75;

    const loop = Animated.loop(
      Animated.parallel([
        // Heart: quick squeeze then relax
        Animated.sequence([
          Animated.timing(heartScale, {
            toValue: 1.22,
            duration: contractMs,
            easing: Easing.out(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(heartScale, {
            toValue: 1,
            duration: expandMs,
            easing: Easing.in(Easing.quad),
            useNativeDriver: true,
          }),
        ]),
        // Ring: expand and fade out on each beat
        Animated.sequence([
          Animated.parallel([
            Animated.timing(ringScale, {
              toValue: 1.7,
              duration: beatMs * 0.6,
              easing: Easing.out(Easing.quad),
              useNativeDriver: true,
            }),
            Animated.timing(ringOpacity, {
              toValue: 0.55,
              duration: beatMs * 0.15,
              useNativeDriver: true,
            }),
          ]),
          Animated.timing(ringOpacity, {
            toValue: 0,
            duration: beatMs * 0.4,
            useNativeDriver: true,
          }),
          // Reset ring for next beat without visible jump
          Animated.parallel([
            Animated.timing(ringScale,   {toValue: 1, duration: 0, useNativeDriver: true}),
            Animated.timing(ringOpacity, {toValue: 0, duration: 0, useNativeDriver: true}),
          ]),
        ]),
      ]),
    );

    animRef.current = loop;
    loop.start();

    return () => {
      loop.stop();
      animRef.current = null;
    };
  }, [active, bpm, heartScale, ringScale, ringOpacity]);

  return (
    <View style={styles.pulseWrap}>
      {/* Expanding ring */}
      <Animated.View
        style={[
          styles.pulseRing,
          {
            transform: [{scale: ringScale}],
            opacity: ringOpacity,
          },
        ]}
      />
      {/* Beating heart core */}
      <Animated.View
        style={[styles.pulseCore, {transform: [{scale: heartScale}]}]}>
        <Text style={styles.heartEmoji}>♥</Text>
      </Animated.View>
    </View>
  );
}

export default function HBScreen({navigation}) {
  const {user} = useAuth();

  // Backend data (always polled — used by guardians and as fallback for patients)
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  // Phone BLE state (patients only — direct sensor connection)
  // bleReading = {bpm: number, ts: number} so every notification triggers a re-render
  const [bleReading, setBleReading] = useState(null);
  const [bleStatus, setBleStatus] = useState('idle'); // idle|scanning|connecting|connected|disconnected|error
  const [bleError, setBleError] = useState('');
  const [bleCount, setBleCount] = useState(0); // total BLE notifications received

  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const isPatient = user?.role === 'User';
  const targetUserId = isHelper ? user?.patient_id : user?.user_id;
  const targetLabel = isHelper ? user?.patient_name : user?.full_name;

  const displayReading = reading?.latest_reading || reading;

  // ── Backend polling ──────────────────────────────────────
  const loadReading = useCallback(async () => {
    if (!targetUserId) {
      setLoading(false);
      setRefreshing(false);
      setReading(null);
      return;
    }
    try {
      const data = await fetchLiveHeartbeat(targetUserId);
      setReading(data);
      setError('');
    } catch (err) {
      setError(err.message || 'Unable to load heartbeat data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [targetUserId]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadReading();
  }, [loadReading]);

  // ── Focus: start polling + BLE ───────────────────────────
  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      let stopBle = null;

      // Backend polling (always)
      setLoading(true);
      loadReading();
      const timer = setInterval(() => {
        if (isActive) {
          loadReading();
        }
      }, POLL_INTERVAL_MS);

      // Phone BLE — patient only
      if (isPatient && targetUserId) {
        requestBlePermissions().then(granted => {
          if (!isActive) {
            return;
          }
          if (!granted) {
            setBleError('Bluetooth permission denied. Enable in phone settings.');
            setBleStatus('error');
            return;
          }
          stopBle = startHeartRateMonitor({
            patientId: targetUserId,
            threshold: reading?.threshold || 90,
            onBpm: packet => {
              if (isActive) {
                setBleReading(packet); // {bpm, ts} — new object every time
                setBleCount(n => n + 1);
                setBleError('');
              }
            },
            onStatus: status => {
              if (isActive) {
                setBleStatus(status);
                if (status === 'disconnected' || status === 'error') {
                  setBleReading(null);
                }
              }
            },
            onError: msg => {
              if (isActive) {
                setBleError(msg);
                setBleStatus('error');
                setBleReading(null);
              }
            },
          });
        });
      }

      return () => {
        isActive = false;
        clearInterval(timer);
        if (stopBle) {
          stopBle();
        }
        setBleReading(null);
        setBleStatus('idle');
        setBleError('');
        setBleCount(0);
      };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [loadReading, isPatient, targetUserId]),
  );

  // ── Derived display values ───────────────────────────────
  const bleConnected = bleStatus === 'connected';

  // For patients: prefer live BLE BPM; fall back to backend reading.
  // For guardians: always use backend reading (they aren't wearing the sensor).
  const live = isPatient ? bleConnected : Boolean(reading?.sensor_connected);

  const bleBpm = bleReading?.bpm ?? null;

  const bpmText =
    (bleBpm ?? reading?.heart_rate ?? displayReading?.heart_rate) != null
      ? String(bleBpm ?? reading?.heart_rate ?? displayReading?.heart_rate)
      : '--';

  const statusText = (() => {
    if (isPatient) {
      if (bleConnected) {return 'Sensor Connected';}
      if (bleStatus === 'scanning') {return 'Scanning…';}
      if (bleStatus === 'connecting') {return 'Connecting…';}
      if (bleStatus === 'disconnected') {return 'Sensor Disconnected';}
      if (bleStatus === 'error') {return 'Connection Failed';}
      return 'Waiting for Sensor';
    }
    // Guardian/Caregiver
    if (reading?.sensor_connected) {return 'Sensor Connected';}
    if (reading?.status === 'no_data' || !reading) {return 'Waiting for Sensor';}
    return 'Sensor Offline';
  })();

  const statusHint = reading?.alert_triggered
    ? 'Heart rate is above the configured threshold.'
    : bleConnected && bleReading?.ts
    ? `Live · ${bleCount} packets · ${new Date(bleReading.ts).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'})}`
    : live && !isPatient && reading?.last_seen_seconds_ago != null
    ? `Live · last reading ${reading.last_seen_seconds_ago}s ago`
    : live
    ? 'Live data is arriving from the sensor.'
    : isPatient
    ? 'Make sure Bluetooth is on and the Polar H10 is worn on your chest.'
    : 'Open the sensor on the patient\'s phone to start the live feed.';

  const metricCards = useMemo(
    () => [
      {
        label: 'Threshold',
        value: reading?.threshold != null ? `${reading.threshold} BPM` : '--',
      },
      {
        label: 'Last Seen',
        value: formatLastSeen(reading?.last_seen_at, reading?.last_seen_seconds_ago),
      },
      {
        label: 'Source',
        value: bleConnected ? 'Phone BLE' : reading?.source || '--',
      },
    ],
    [reading, bleConnected],
  );

  return (
    <ScreenBg>
      <TopBar navigation={navigation} title="HB Monitor" />

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={COLORS.white}
          />
        }>
        <View style={styles.heroCard}>
          {loading && !reading ? (
            <View style={styles.loadingState}>
              <ActivityIndicator size="large" color="#ff6b6b" />
              <Text style={styles.loadingText}>Connecting to heartbeat sensor...</Text>
            </View>
          ) : null}

          <View style={styles.heroTopRow}>
            <View style={[styles.livePill, live ? styles.livePillActive : styles.livePillIdle]}>
              <View style={[styles.liveDot, live ? styles.liveDotActive : styles.liveDotIdle]} />
              <Text style={styles.livePillText}>{statusText}</Text>
            </View>
            <Text style={styles.patientName} numberOfLines={1}>
              {targetLabel || 'No patient linked'}
            </Text>
          </View>

          <View style={styles.heartRow}>
            <HeartPulse active={live} bpm={bleBpm ?? reading?.heart_rate} />
            <View style={styles.bpmBlock}>
              <Text style={styles.bpmValue}>{bpmText}</Text>
              <Text style={styles.bpmLabel}>BPM</Text>
              <Text style={styles.bpmMeta}>{statusHint}</Text>
            </View>
          </View>
        </View>

        <SectionTitle hint={bleConnected ? 'Live from your Polar H10' : 'Auto refreshes every 3 seconds'}>
          Live Reading
        </SectionTitle>

        {!targetUserId ? (
          <View style={styles.emptyStateCard}>
            <Text style={styles.emptyStateTitle}>No patient linked</Text>
            <Text style={styles.emptyStateText}>
              Link a patient account first so live heartbeat readings can appear here.
            </Text>
          </View>
        ) : null}

        <View style={styles.metricsGrid}>
          {metricCards.map(item => (
            <View key={item.label} style={styles.metricCard}>
              <Text style={styles.metricLabel}>{item.label}</Text>
              <Text style={styles.metricValue} numberOfLines={2}>
                {item.value}
              </Text>
            </View>
          ))}
        </View>

        {reading?.alert_triggered ? (
          <View style={styles.alertCard}>
            <Text style={styles.alertTitle}>Attention needed</Text>
            <Text style={styles.alertText}>
              The current heart rate is above the configured threshold and helpers may be notified.
            </Text>
          </View>
        ) : null}

        {bleError ? (
          <View style={styles.bleErrorCard}>
            <Text style={styles.bleErrorTitle}>Bluetooth</Text>
            <Text style={styles.bleErrorText}>{bleError}</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <DarkBtn title="Refresh Now" onPress={onRefresh} style={styles.actionBtn} disabled={refreshing} />

        <BackBtn onPress={() => navigation.navigate('Dashboard')} />
      </ScrollView>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 12,
    paddingBottom: Platform.OS === 'ios' ? 44 : 28,
    gap: 14,
  },
  heroCard: {
    backgroundColor: 'rgba(28,33,32,0.94)',
    borderRadius: 28,
    padding: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    shadowColor: '#000',
    shadowOpacity: 0.22,
    shadowRadius: 18,
    shadowOffset: {width: 0, height: 12},
    elevation: 8,
  },
  heroTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 18,
  },
  livePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  livePillActive: {
    backgroundColor: 'rgba(34,197,94,0.14)',
  },
  livePillIdle: {
    backgroundColor: 'rgba(239,68,68,0.12)',
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  liveDotActive: {
    backgroundColor: '#4ade80',
  },
  liveDotIdle: {
    backgroundColor: '#f87171',
  },
  livePillText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '600',
  },
  patientName: {
    color: 'rgba(255,255,255,0.72)',
    fontSize: 13,
    fontWeight: '500',
    flex: 1,
    textAlign: 'right',
  },
  heartRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 18,
  },
  pulseWrap: {
    width: 150,
    height: 150,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pulseRing: {
    position: 'absolute',
    width: 118,
    height: 118,
    borderRadius: 59,
    backgroundColor: 'rgba(248,113,113,0.55)',
  },
  pulseCore: {
    width: 92,
    height: 92,
    borderRadius: 46,
    backgroundColor: 'rgba(127,29,29,0.96)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  heartEmoji: {
    color: '#ff6b6b',
    fontSize: 34,
  },
  bpmBlock: {
    flex: 1,
  },
  bpmValue: {
    color: COLORS.white,
    fontSize: 58,
    lineHeight: 60,
    fontWeight: '700',
  },
  bpmLabel: {
    color: '#ff8a8a',
    fontSize: 18,
    fontWeight: '700',
    marginTop: 2,
    marginBottom: 6,
  },
  bpmMeta: {
    color: 'rgba(255,255,255,0.68)',
    fontSize: 13,
    lineHeight: 18,
  },
  loadingState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 18,
  },
  loadingText: {
    marginTop: 10,
    color: 'rgba(255,255,255,0.78)',
    fontSize: 13,
    fontWeight: '500',
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  metricCard: {
    flex: 1,
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  metricLabel: {
    color: 'rgba(255,255,255,0.48)',
    fontSize: 11,
    fontWeight: '500',
    marginBottom: 6,
  },
  metricValue: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 19,
  },
  alertCard: {
    backgroundColor: 'rgba(239,68,68,0.14)',
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(239,68,68,0.28)',
  },
  alertTitle: {
    color: '#ffb4b4',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
  },
  alertText: {
    color: 'rgba(255,255,255,0.86)',
    fontSize: 12,
    lineHeight: 18,
  },
  emptyStateCard: {
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  emptyStateTitle: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
  },
  emptyStateText: {
    color: 'rgba(255,255,255,0.72)',
    fontSize: 12,
    lineHeight: 18,
  },
  bleErrorCard: {
    backgroundColor: 'rgba(251,191,36,0.10)',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: 'rgba(251,191,36,0.22)',
  },
  bleErrorTitle: {
    color: '#fcd34d',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 2,
  },
  bleErrorText: {
    color: 'rgba(255,255,255,0.82)',
    fontSize: 12,
  },
  errorCard: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  errorText: {
    color: '#ffd1d1',
    fontSize: 12,
  },
  actionBtn: {
    marginTop: 0,
  },
});
