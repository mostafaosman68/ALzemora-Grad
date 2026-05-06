import React, {useCallback, useMemo, useState} from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Platform,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {ScreenBg, TopBar, DarkBtn, BackBtn, COLORS, SectionTitle} from '../components/UI';
import {useAuth} from '../../App';
import {fetchLiveHeartbeat, reportHeartbeat} from '../services/heartbeatService';

const POLL_INTERVAL_MS = 3000;

function formatLastSeen(lastSeenAt, secondsAgo) {
  if (!lastSeenAt) return 'No readings yet';

  const date = new Date(lastSeenAt);
  if (Number.isNaN(date.getTime())) {
    return 'No readings yet';
  }

  const seenTime = date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  if (typeof secondsAgo === 'number') {
    return `${seenTime} • ${secondsAgo}s ago`;
  }

  return seenTime;
}

function HeartPulse({active}) {
  return (
    <View style={[styles.pulseWrap, active && styles.pulseWrapActive]}>
      <View style={[styles.pulseRing, active && styles.pulseRingActive]} />
      <View style={styles.pulseCore}>
        <Text style={styles.heartEmoji}>♥</Text>
      </View>
    </View>
  );
}

export default function HBScreen({navigation}) {
  const {user} = useAuth();
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const targetUserId = isHelper ? user?.patient_id : user?.user_id;
  const targetLabel = isHelper ? user?.patient_name : user?.full_name;

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

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      setLoading(true);
      loadReading();

      const timer = setInterval(() => {
        if (isActive) {
          loadReading();
        }
      }, POLL_INTERVAL_MS);

      return () => {
        isActive = false;
        clearInterval(timer);
      };
    }, [loadReading]),
  );

  const live = Boolean(reading?.sensor_connected);
  const bpmText = reading?.heart_rate != null ? String(reading.heart_rate) : '--';
  const statusText = live ? 'Sensor Connected' : reading?.status === 'no_data' ? 'Waiting for Sensor' : 'Sensor Offline';
  const statusHint = reading?.alert_triggered
    ? 'Heart rate is above the configured threshold.'
    : live
      ? 'Live data is arriving from the sensor.'
      : 'Open the sensor device to start the live feed.';

  const metricCards = useMemo(() => ([
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
      value: reading?.source || 'sensor',
    },
  ]), [reading]);

  const handleDemoReading = async () => {
    if (!targetUserId) return;

    try {
      setRefreshing(true);
      await reportHeartbeat({
        patientId: targetUserId,
        heartRate: 67,
        threshold: reading?.threshold || 120,
        source: 'demo',
      });
      await loadReading();
    } catch (err) {
      setError(err.message || 'Unable to send demo reading');
      setRefreshing(false);
    }
  };

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
            <HeartPulse active={live} />
            <View style={styles.bpmBlock}>
              <Text style={styles.bpmValue}>{bpmText}</Text>
              <Text style={styles.bpmLabel}>BPM</Text>
              <Text style={styles.bpmMeta}>{statusHint}</Text>
            </View>
          </View>
        </View>

        <SectionTitle hint="Auto refreshes every 3 seconds">Live Reading</SectionTitle>

        <View style={styles.metricsGrid}>
          {metricCards.map((item) => (
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

        {error ? (
          <View style={styles.errorCard}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        <View style={styles.actionsRow}>
          <DarkBtn title="Refresh Now" onPress={onRefresh} style={styles.actionBtn} disabled={refreshing} />
          <TouchableOpacity
            style={styles.demoBtn}
            onPress={handleDemoReading}
            activeOpacity={0.85}
            disabled={!targetUserId || refreshing}>
            <Text style={styles.demoBtnText}>Send Demo Reading</Text>
          </TouchableOpacity>
        </View>

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
  pulseWrapActive: {
    transform: [{scale: 1}],
  },
  pulseRing: {
    position: 'absolute',
    width: 118,
    height: 118,
    borderRadius: 59,
    backgroundColor: 'rgba(239,68,68,0.15)',
  },
  pulseRingActive: {
    backgroundColor: 'rgba(248,113,113,0.22)',
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
  actionsRow: {
    gap: 10,
  },
  actionBtn: {
    marginTop: 0,
  },
  demoBtn: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    paddingVertical: 14,
    alignItems: 'center',
  },
  demoBtnText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '600',
  },
});
