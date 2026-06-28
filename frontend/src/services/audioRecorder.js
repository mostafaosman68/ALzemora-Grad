import {NativeModules} from 'react-native';

const {RNAudioRecord} = NativeModules;

// Configuration state
let recordingConfig = {
  sampleRate: 16000,
  channels: 1,
  bitsPerSample: 16,
  wavFile: 'recording.wav',
};

const AudioRecorderService = {
  /**
   * Initialize audio recording with custom config
   * @param {Object} config - Configuration object
   * @param {number} config.sampleRate - Sample rate (default: 16000)
   * @param {number} config.channels - Number of channels (default: 1)
   * @param {number} config.bitsPerSample - Bits per sample (default: 16)
   * @param {string} config.wavFile - Output filename (default: recording.wav)
   */
  init: async (config = {}) => {
    try {
      if (!RNAudioRecord) {
        throw new Error('RNAudioRecord native module is not available');
      }

      recordingConfig = {
        sampleRate: config.sampleRate || 16000,
        channels: config.channels || 1,
        bitsPerSample: config.bitsPerSample || 16,
        wavFile: config.wavFile || 'recording.wav',
      };

      RNAudioRecord.init({
        sampleRate: recordingConfig.sampleRate,
        channels: recordingConfig.channels,
        bitsPerSample: recordingConfig.bitsPerSample,
        audioSource: 'default', // For Android
        wavFile: recordingConfig.wavFile,
      });
    } catch (error) {
      console.error('AudioRecorder init error:', error);
      throw error;
    }
  },

  /**
   * Start recording audio
   */
  start: async () => {
    try {
      if (!RNAudioRecord) {
        throw new Error('RNAudioRecord native module is not available');
      }

      await RNAudioRecord.start();
    } catch (error) {
      console.error('AudioRecorder start error:', error);
      throw error;
    }
  },

  /**
   * Stop recording and return the file path
   * @returns {Promise<string>} Path to the recorded audio file
   */
  stop: async () => {
    try {
      if (!RNAudioRecord) {
        throw new Error('RNAudioRecord native module is not available');
      }

      const result = await RNAudioRecord.stop();

      if (!result) {
        console.warn('AudioRecord.stop() returned no result');
        return null;
      }

      // The result is typically the file path
      // If it's an object with a path property, extract it
      const filePath = typeof result === 'string' ? result : result.path || result;

      if (!filePath) {
        console.warn('No file path returned from AudioRecord.stop()');
        return null;
      }

      console.log('Recording stopped. File saved at:', filePath);
      return filePath;
    } catch (error) {
      console.error('AudioRecorder stop error:', error);
      throw error;
    }
  },

  /**
   * Check if audio is being recorded
   * @returns {boolean} True if recording is in progress
   */
  isRecording: async () => {
    try {
      // Note: react-native-audio-record doesn't have a built-in isRecording method
      // This is a placeholder. You might need to track this manually in your component
      return false;
    } catch (error) {
      console.error('AudioRecorder isRecording error:', error);
      return false;
    }
  },

  /**
   * Cancel the current recording
   */
  cancel: async () => {
    try {
      if (!RNAudioRecord) {
        throw new Error('RNAudioRecord native module is not available');
      }

      await RNAudioRecord.stop();
    } catch (error) {
      console.error('AudioRecorder cancel error:', error);
      throw error;
    }
  },
};

export default AudioRecorderService;
