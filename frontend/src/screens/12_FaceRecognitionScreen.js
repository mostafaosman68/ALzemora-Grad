import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  Image,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Dimensions,
  Platform,
} from 'react-native';
import {ScreenBg, TopBar, COLORS} from '../components/UI';
import {useAuth} from '../../App';
import {BASE_URL} from '../config';

const {width, height} = Dimensions.get('window');
const POLL_INTERVAL_MS = 150;

export default function FaceRecognitionScreen({navigation}) {
  const {user} = useAuth();
  const [status, setStatus] = useState('starting'); // 'starting' | 'running' | 'error' | 'stopping'
  const [frameTs, setFrameTs] = useState(Date.now());
  const [frameReady, setFrameReady] = useState(false);
  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  const targetUserId = user?.patient_id || user?.user_id;

  const stopRecognition = useCallback(async () => {
    clearInterval(pollRef.current);
    try {
      await fetch(`${BASE_URL}/stop-recognition`, {method: 'POST'});
    } catch (_) {}
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    const start = async () => {
      if (!targetUserId) {
        setStatus('error');
        Alert.alert('Error', 'Could not determine user. Please log in again.');
        return;
      }

      try {
        const res = await fetch(`${BASE_URL}/start-recognition`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', Accept: 'application/json'},
          body: JSON.stringify({user_id: targetUserId}),
        });
        const data = await res.json();

        if (!res.ok) {
          if (!mountedRef.current) return;
          setStatus('error');
          Alert.alert('Failed', data.detail || 'Could not start recognition');
          return;
        }

        if (data.status === 'no_people') {
          if (!mountedRef.current) return;
          setStatus('error');
          Alert.alert(
            'No People Registered',
            data.message,
            [
              {text: 'Add Friends', onPress: () => navigation.replace('AddFriend')},
              {text: 'Cancel', style: 'cancel', onPress: () => navigation.goBack()},
            ],
          );
          return;
        }

        if (!mountedRef.current) return;
        setStatus('running');

        // Start polling for frames
        pollRef.current = setInterval(() => {
          if (mountedRef.current) {
            setFrameTs(Date.now());
          }
        }, POLL_INTERVAL_MS);

      } catch (e) {
        if (!mountedRef.current) return;
        setStatus('error');
        Alert.alert('Connection Error', 'Cannot reach the backend. Make sure you are on the same Wi-Fi.');
      }
    };

    start();

    return () => {
      mountedRef.current = false;
      stopRecognition();
    };
  }, [targetUserId, stopRecognition]);

  const handleStop = async () => {
    setStatus('stopping');
    await stopRecognition();
    navigation.goBack();
  };

  const frameUri = `${BASE_URL}/latest-frame?t=${frameTs}`;

  return (
    <ScreenBg>
      <TopBar
        navigation={navigation}
        title="Face Recognition"
        leftElement={
          <TouchableOpacity
            onPress={handleStop}
            activeOpacity={0.8}
            style={styles.backBtn}>
            <Text style={styles.backText}>✕</Text>
          </TouchableOpacity>
        }
      />

      <View style={styles.feedContainer}>
        {status === 'starting' && (
          <View style={styles.centeredOverlay}>
            <ActivityIndicator size="large" color={COLORS.teal} />
            <Text style={styles.statusText}>Starting recognition...</Text>
          </View>
        )}

        {status === 'error' && (
          <View style={styles.centeredOverlay}>
            <Text style={styles.errorIcon}>⚠️</Text>
            <Text style={styles.statusText}>Recognition could not start.</Text>
          </View>
        )}

        {status === 'stopping' && (
          <View style={styles.centeredOverlay}>
            <ActivityIndicator size="large" color={COLORS.teal} />
            <Text style={styles.statusText}>Stopping...</Text>
          </View>
        )}

        {status === 'running' && (
          <Image
            key={frameTs}
            source={{uri: frameUri}}
            style={styles.frame}
            resizeMode="contain"
            onLoad={() => {
              if (!frameReady) setFrameReady(true);
            }}
            onError={() => {}}
          />
        )}

        {status === 'running' && !frameReady && (
          <View style={styles.centeredOverlay}>
            <ActivityIndicator size="large" color={COLORS.teal} />
            <Text style={styles.statusText}>Waiting for camera...</Text>
          </View>
        )}
      </View>

      <View style={styles.bottomBar}>
        <View style={styles.statusPill}>
          <View style={[styles.dot, status === 'running' ? styles.dotGreen : styles.dotGray]} />
          <Text style={styles.pillText}>
            {status === 'running' ? 'Live' : status === 'starting' ? 'Starting…' : 'Stopped'}
          </Text>
        </View>

        <TouchableOpacity
          style={styles.stopBtn}
          onPress={handleStop}
          activeOpacity={0.8}
          disabled={status === 'stopping'}>
          <Text style={styles.stopBtnText}>
            {status === 'stopping' ? 'Stopping…' : 'Stop Recognition'}
          </Text>
        </TouchableOpacity>
      </View>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  feedContainer: {
    flex: 1,
    marginHorizontal: 12,
    marginTop: 10,
    borderRadius: 18,
    overflow: 'hidden',
    backgroundColor: '#000',
    justifyContent: 'center',
    alignItems: 'center',
  },
  frame: {
    width: '100%',
    height: '100%',
  },
  centeredOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  statusText: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 14,
    fontWeight: '500',
  },
  errorIcon: {
    fontSize: 36,
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 16,
    marginTop: 10,
    marginBottom: Platform.OS === 'ios' ? 32 : 16,
    gap: 12,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(255,255,255,0.08)',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  dotGreen: {
    backgroundColor: '#4cde80',
  },
  dotGray: {
    backgroundColor: 'rgba(255,255,255,0.3)',
  },
  pillText: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: '600',
  },
  stopBtn: {
    flex: 1,
    backgroundColor: '#c0392b',
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: 'center',
  },
  stopBtnText: {
    color: COLORS.white,
    fontSize: 14,
    fontWeight: '700',
  },
  backBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backText: {
    color: COLORS.white,
    fontSize: 16,
    fontWeight: '700',
  },
});
