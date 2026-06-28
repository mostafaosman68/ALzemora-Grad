import React, {useState} from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
  Platform,
} from 'react-native';
import Svg, {
  Rect,
  Line,
  Circle,
  Ellipse,
  Text as SvgText,
  Defs,
  RadialGradient,
  Stop,
  AnimatedCircle,
} from 'react-native-svg';
import {ScreenBg, TopBar, DarkBtn, BackBtn, COLORS} from '../components/UI';

const {width, height} = Dimensions.get('window');
const MAP_H = height * 0.5;

const PINS = [
  {x: 96,  y: MAP_H * 0.37, color: '#f59e0b'},
  {x: 160, y: MAP_H * 0.41, color: '#f59e0b'},
  {x: 228, y: MAP_H * 0.35, color: '#f59e0b'},
  {x: 260, y: MAP_H * 0.60, color: '#f59e0b'},
  {x: 128, y: MAP_H * 0.62, color: '#f59e0b'},
];
const USER_PIN = {x: 193, y: MAP_H * 0.52};

export default function GeoLocationScreen({navigation}) {
  const [tracking, setTracking] = useState(false);

  return (
    <ScreenBg>
      <TopBar navigation={navigation} />

      {/* Map */}
      <View style={styles.mapContainer}>
        <Svg width={width} height={MAP_H} viewBox={`0 0 ${width} ${MAP_H}`}>
          {/* Base */}
          <Rect width={width} height={MAP_H} fill="#d4e7f0" />

          {/* Water */}
          <Ellipse
            cx={width / 2} cy={MAP_H / 2}
            rx={width * 0.38} ry={MAP_H * 0.3}
            fill="#a8d4e8" opacity={0.65}
          />

          {/* Horizontal roads */}
          {[0.14, 0.38, 0.58, 0.78].map((frac, i) => (
            <Line
              key={`h${i}`}
              x1={0} y1={MAP_H * frac}
              x2={width} y2={MAP_H * frac}
              stroke="#c0d4de" strokeWidth={i === 0 ? 13 : 7}
            />
          ))}
          {/* Vertical roads */}
          {[0.18, 0.44, 0.72, 0.90].map((frac, i) => (
            <Line
              key={`v${i}`}
              x1={width * frac} y1={0}
              x2={width * frac} y2={MAP_H}
              stroke="#c0d4de" strokeWidth={i === 0 ? 13 : 7}
            />
          ))}

          {/* City blocks */}
          {[
            [0.20, 0.16, 0.22, 0.20],
            [0.46, 0.16, 0.24, 0.20],
            [0.20, 0.40, 0.22, 0.16],
            [0.46, 0.40, 0.24, 0.16],
            [0.74, 0.16, 0.14, 0.20],
            [0.74, 0.40, 0.14, 0.16],
          ].map(([xl, yt, wr, hr], i) => (
            <Rect
              key={`b${i}`}
              x={width * xl} y={MAP_H * yt}
              width={width * wr} height={MAP_H * hr}
              fill="#bed5e0" rx={4} opacity={0.8}
            />
          ))}

          {/* Radius circle */}
          <Circle
            cx={193} cy={MAP_H * 0.52}
            r={MAP_H * 0.32}
            fill="rgba(59,130,246,0.12)"
            stroke="rgba(59,130,246,0.55)"
            strokeWidth={1.5}
            strokeDasharray="6,3"
          />

          {/* Location pins */}
          {PINS.map((p, i) => (
            <React.Fragment key={i}>
              <Circle cx={p.x} cy={p.y} r={10} fill={p.color} stroke="#fff" strokeWidth={2} />
            </React.Fragment>
          ))}

          {/* User pin with pulse */}
          <Circle
            cx={USER_PIN.x} cy={USER_PIN.y}
            r={16} fill="none"
            stroke="rgba(59,130,246,0.4)"
            strokeWidth={2}
          />
          <Circle
            cx={USER_PIN.x} cy={USER_PIN.y}
            r={10} fill="#3b82f6"
            stroke="#fff" strokeWidth={3}
          />

          {/* Labels */}
          <SvgText x={85}  y={MAP_H * 0.26} fontSize={9} fill="#5a7a8a" fontWeight="600">WYNYARD</SvgText>
          <SvgText x={168} y={MAP_H * 0.54} fontSize={9} fill="#5a7a8a">CBD</SvgText>
          <SvgText x={10}  y={MAP_H * 0.47} fontSize={9} fill="#5a7a8a">Darling</SvgText>
          <SvgText x={10}  y={MAP_H * 0.52} fontSize={9} fill="#5a7a8a">Island</SvgText>
        </Svg>

        {/* Live badge */}
        {tracking && (
          <View style={styles.liveBadge}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>Live Tracking</Text>
          </View>
        )}
      </View>

      {/* Bottom panel */}
      <View style={styles.bottomPanel}>
        {/* Last seen */}
        <View style={styles.infoRow}>
          <View>
            <Text style={styles.infoSub}>Last Seen</Text>
            <Text style={styles.infoMain}>Sydney CBD, Australia</Text>
          </View>
          <Text style={styles.infoEmoji}>📍</Text>
        </View>

        <DarkBtn
          title={tracking ? '⏹  Stop Tracking' : '▶  Track User!'}
          onPress={() => setTracking(t => !t)}
          style={styles.trackBtn}
        />

        <BackBtn
          onPress={() => navigation.navigate('Dashboard')}
          label="← Back to Dashboard"
        />
      </View>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  mapContainer: {
    width: '100%',
    height: MAP_H,
    overflow: 'hidden',
  },
  liveBadge: {
    position: 'absolute',
    top: 12,
    right: 12,
    backgroundColor: 'rgba(28,33,32,0.85)',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#4ade80',
  },
  liveText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#fff',
  },
  bottomPanel: {
    flex: 1,
    paddingHorizontal: 18,
    paddingTop: 20,
    paddingBottom: Platform.OS === 'ios' ? 36 : 20,
    gap: 12,
  },
  infoRow: {
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  infoSub: {
    fontSize: 11,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.5)',
    marginBottom: 2,
  },
  infoMain: {
    fontSize: 15,
    fontWeight: '600',
    color: '#fff',
  },
  infoEmoji: {fontSize: 22},
  trackBtn: {marginTop: 0},
});
