import type { ReactNode } from 'react';
import { X, MapPin, Activity } from 'lucide-react';
import { ApiError } from '../lib/api';
import { Badge } from '../components/ui';

export interface Department { id:string; name:string; code:string; active:boolean }
export interface Course { id:string; department_id:string; semester_id:string|null; course_code:string; name:string; description:string; attendance_threshold:number; active:boolean }
export interface Semester { id:string; academic_year_id:string; name:string; starts_on:string; ends_on:string }
export interface Year { id:string; name:string; starts_on:string; ends_on:string; active:boolean }
export interface Section { id:string; course_id:string; name:string }
export interface StudentRow { id:string; user_id:string; student_number:string; full_name:string; email:string; department_id:string; program:string; semester_id:string|null; enrollment_status:string; active:boolean; activated:boolean; face_enrolled:boolean }
export interface TeacherRow { id:string; user_id:string; employee_number:string; full_name:string; email:string; department_id:string; active:boolean; activated:boolean }
export interface FormResult { activation_token:string; activation_path:string; expires_in_days?:number; expires_in_hours?:number }
export interface LocationRow { id:string;department_id:string;name:string;latitude:number;longitude:number;radius_m:number;max_accuracy_m:number;active:boolean }
export interface SessionRow { id:string;course_id:string;course_code:string;course_name:string;section_id:string|null;location_id:string;location_name:string;title:string;starts_at:string;ends_at:string;grace_minutes:number;cancelled:boolean;finalized:boolean }
export interface AttendanceRow { id:string;student_id:string;student_number:string;student_name:string;session_id:string;course_id:string;course_code:string;course_name:string;status:string;marked_at:string;reason:string|null;updated_by:string|null }
export interface CorrectionRow { id:string;student_id:string;student_number:string;student_name:string;session_id:string;course_name:string;requested_status:string;reason:string;status:string;submitted_by:string;decision_reason:string|null;created_at:string }
export interface AuditRow { id:string;actor_user_id:string|null;action:string;entity_type:string;entity_id:string|null;details:Record<string,unknown>;created_at:string }

export function PanelTitle({icon,eyebrow,title,count}:{icon:ReactNode;eyebrow:string;title:string;count?:number}) {
  return <div className="panel-title"><span className="panel-icon">{icon}</span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{count!==undefined&&<Badge>{count}</Badge>}</div>;
}
export function Modal({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="modal-card" role="dialog" aria-modal="true" aria-label={title}><div className="modal-heading"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={18}/></button></div>{children}</section></div>;
}
export function MapPinIcon(){return <MapPin size={17}/>;}
export function ActivityBadge(){return <Activity size={17} className="muted-icon"/>;}
export function statusTone(value:string){return value==='present'||value==='approved'?'success':value==='late'||value==='pending'?'warning':value==='excused'?'info':'danger';}
export function errorText(cause:unknown){return cause instanceof ApiError?cause.message:cause instanceof Error?cause.message:'The request could not be completed. Please try again.';}
export function localDateTimeToUtc(value:string,timeZone:string){
  if(!value)throw new Error('Choose both a session start and end time.');
  const [datePart,timePart]=value.split('T');const [year,month,day]=datePart.split('-').map(Number);const [hour,minute]=timePart.split(':').map(Number);
  const desired=Date.UTC(year,month-1,day,hour,minute);let guess=desired;
  const formatter=new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  for(let i=0;i<3;i++){const parts=Object.fromEntries(formatter.formatToParts(new Date(guess)).map(part=>[part.type,part.value]));const observed=Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day),Number(parts.hour),Number(parts.minute));const delta=observed-desired;if(delta===0)break;guess-=delta;}
  const check=formatter.formatToParts(new Date(guess));const parts=Object.fromEntries(check.map(part=>[part.type,part.value]));
  if(Number(parts.year)!==year||Number(parts.month)!==month||Number(parts.day)!==day||Number(parts.hour)!==hour||Number(parts.minute)!==minute)throw new Error('That local time does not exist in the campus timezone because of a daylight-saving transition. Choose another time.');
  return new Date(guess).toISOString();
}
