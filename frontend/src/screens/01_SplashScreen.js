import React, {useEffect} from 'react';
import {
  View,
  Image,
  Text,
  StyleSheet,
  Dimensions,
  TouchableOpacity,
  Animated,
} from 'react-native';
import {COLORS, logo} from '../components/UI';

const {width, height} = Dimensions.get('window');

export default function SplashScreen({navigation}) {
  const scaleAnim   = new Animated.Value(0.5);
  const opacityAnim = new Animated.Value(0);
  const barWidth    = new Animated.Value(0);

  useEffect(() => {
    // Logo pop-in animation
    Animated.parallel([
      Animated.spring(scaleAnim, {
        toValue: 1,
        friction: 5,
        tension: 80,
        useNativeDriver: true,
      }),
      Animated.timing(opacityAnim, {
        toValue: 1,
        duration: 600,
        useNativeDriver: true,
      }),
    ]).start();

    // Loading bar
    Animated.timing(barWidth, {
      toValue: 140,
      duration: 2400,
      useNativeDriver: false,
    }).start();

    // Auto-navigate after 2.6s
    const timer = setTimeout(
      () => navigation.replace('AccountType'),
      2600,
    );
    return () => clearTimeout(timer);
  }, []);

  return (
    <TouchableOpacity
      activeOpacity={1}
      style={styles.container}
      onPress={() => navigation.replace('AccountType')}>

      {/* Background layers */}
      <View style={styles.bgDark} />
      <View style={styles.bgMid} />

      {/* Brain logo */}
      <Animated.View
        style={[
          styles.logoWrapper,
          {opacity: opacityAnim, transform: [{scale: scaleAnim}]},
        ]}>
        <Image source={logo} style={styles.logo} resizeMode="contain" />
      </Animated.View>

      {/* Loading bar */}
      <View style={styles.barTrack}>
        <Animated.View style={[styles.barFill, {width: barWidth}]} />
      </View>

      {/* Tap hint */}
      <Text style={styles.hint}>Tap to continue</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.bgDark,
  },
  bgDark: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: COLORS.bgDark,
  },
  bgMid: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: height * 0.5,
    backgroundColor: COLORS.bgDark,
    opacity: 0.45,
  },
  logoWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 60,
  },
  logo: {
    width: width * 0.65,
    height: width * 0.65,
  },
  barTrack: {
    position: 'absolute',
    bottom: 100,
    width: 140,
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    backgroundColor: COLORS.teal,
    borderRadius: 2,
  },
  hint: {
    position: 'absolute',
    bottom: 68,
    fontSize: 11,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.35)',
    letterSpacing: 1,
  },
});
