
import { API_BASE } from './socialApi';

export type LoginMethod = 'email' | 'phone';

export type SignupPayload = {
  username: string;
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  display_nickname: string;
  phone_country_code: string;
  phone_number: string;
  otp_challenge_id: string;
  legal_accepted: boolean;
};

export type AuthSuccessResponse = {
  success: boolean;
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    username: string;
    phone?: string;
  };
};

export type ForgotPasswordMode = 'email' | 'phone';

export type ForgotPasswordResponse = {
  success: boolean;
  message: string;
  challenge_id?: string;
  expires_at?: string;
};

async function authRequest<T>(path: string, body: Record<string, unknown>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Network unavailable. Please check your connection and try again.');
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' && 'detail' in payload
      ? String(payload.detail)
      : 'Authentication request failed';
    throw new Error(detail);
  }

  return payload as T;
}

export async function sendSignupOtp(countryCode: string, phoneNumber: string): Promise<{ challenge_id: string; expires_at: string; message: string }> {
  return authRequest('/api/auth/otp/send', {
    country_code: countryCode,
    phone_number: phoneNumber,
  });
}

export async function verifySignupOtp(challengeId: string, otpCode: string): Promise<{ success: boolean; challenge_id: string; phone: string; message: string }> {
  return authRequest('/api/auth/otp/verify', {
    challenge_id: challengeId,
    otp_code: otpCode,
  });
}

export async function checkSignupAvailability(email: string, username: string): Promise<{ success: boolean; email_available: boolean; username_available: boolean }> {
  return authRequest('/api/auth/availability', {
    email,
    username,
  });
}

export async function signupWithWizard(payload: SignupPayload): Promise<AuthSuccessResponse> {
  return authRequest('/api/auth/signup', payload);
}

export async function loginWithPassword(identity: string, password: string): Promise<AuthSuccessResponse> {
  return authRequest('/api/auth/login', {
    identity,
    password,
  });
}

export async function requestPasswordReset(payload: { mode: ForgotPasswordMode; email?: string; country_code?: string; phone_number?: string }): Promise<ForgotPasswordResponse> {
  return authRequest('/api/auth/forgot-password', payload);
}

export async function verifyPasswordResetOtp(challengeId: string, otpCode: string): Promise<{ success: boolean; challenge_id: string; phone: string; message: string }> {
  return verifySignupOtp(challengeId, otpCode);
}

export function persistAuthSession(response: AuthSuccessResponse): void {
  try {
    window.localStorage.setItem('access_token', response.access_token);
    window.localStorage.setItem('refresh_token', response.refresh_token);
    window.localStorage.setItem('user', JSON.stringify(response.user));
  } catch (error) {
    console.error('Failed to persist auth session', error);
    throw new Error('Unable to persist secure session on this device.');
  }
}
