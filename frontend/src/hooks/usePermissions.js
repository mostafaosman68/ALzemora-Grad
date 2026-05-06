import {useAuth} from '../../App';

// Roles that are allowed to perform write / edit operations.
const CAN_EDIT_ROLES = ['Guardian', 'CareGiver'];

/**
 * Returns RBAC flags derived from the currently authenticated user.
 *
 * canEdit  — true for Guardian and CareGiver; false for User (patient).
 * isPatient — true when the logged-in account is a patient (User role).
 */
export function usePermissions() {
  const {user} = useAuth();
  const canEdit = CAN_EDIT_ROLES.includes(user?.role);
  const isPatient = user?.role === 'User';
  return {canEdit, isPatient};
}
