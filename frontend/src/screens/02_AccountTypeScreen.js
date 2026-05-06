import React from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
} from 'react-native';
import {
  ScreenBg,
  BrandHeader,
  Card,
  DarkBtn,
  Subtitle,
  CardTitle,
  COLORS,
} from '../components/UI';

const ACCOUNT_TYPES = [
  {label: 'Guardian',   desc: 'Manage a loved one with Alzheimer\'s'},
  {label: 'User',       desc: 'Patient account with assisted features'},
  {label: 'CareGiver',  desc: 'Professional caregiver access'},
];

export default function AccountTypeScreen({navigation}) {
  return (  
    <ScreenBg>
      <BrandHeader />

      <Card topRightRadius={60}>
        <ScrollView showsVerticalScrollIndicator={false}>
          <CardTitle>Create account</CardTitle>

          <Subtitle
            text="Already got an Account"
            linkText="Sign in"
            onLinkPress={() => navigation.navigate('Login')}
          />

          <Text style={styles.instruction}>
            Please choose Account type
          </Text>

          {ACCOUNT_TYPES.map(({label, desc}) => (
            <DarkBtn
              key={label}
              title={label}
              onPress={() =>
                navigation.navigate('SignUp', {accountType: label})
              }
              style={styles.typeBtn}
            />
          ))}

          <DarkBtn
            title="Sign Up"
            onPress={() => navigation.navigate('SignUp')}
            style={styles.signUpBtn}
          />
        </ScrollView>
      </Card>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  instruction: {
    fontSize: 16,
    fontWeight: '400',
    color: COLORS.text,
    marginBottom: 18,
    marginTop: 4,
  },
  typeBtn: {
    marginBottom: 14,
    marginTop: 0,
  },
  signUpBtn: {
    marginTop: 16,
    backgroundColor: '#2a4a5c',
  },
});
