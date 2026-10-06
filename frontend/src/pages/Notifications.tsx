import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Check, CheckCheck, Info, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api, formatDate } from '../lib/api';
import { Badge, Card, EmptyState, Loading, Notice, PageHeader } from '../components/ui';
import { errorText } from './admin-shared';

interface NotificationRow{id:string;kind:string;title:string;message:string;link:string;read:boolean;created_at:string}
export function NotificationsPage(){
 const qc=useQueryClient();const [error,setError]=useState('');const query=useQuery({queryKey:['notifications'],queryFn:()=>api<{items:NotificationRow[];total:number;unread:number}>('/notifications?limit=200')});
 async function refresh(){await qc.invalidateQueries({queryKey:['notifications']});await qc.invalidateQueries({queryKey:['notifications','unread-count']});}
 async function mark(id:string){setError('');try{await api(`/notifications/${id}/read`,{method:'PATCH'});await refresh();}catch(cause){setError(errorText(cause));}}
 async function markAll(){setError('');try{await api('/notifications/read-all',{method:'POST'});await refresh();}catch(cause){setError(errorText(cause));}}
 if(query.isLoading)return <Loading label="Loading your notifications…"/>;
 return <main><PageHeader eyebrow="CAMPUS UPDATES" title="Notifications" description="In-app attendance alerts and relevant account updates." actions={!!query.data?.unread&&<button className="button button-secondary" onClick={()=>void markAll()}><CheckCheck size={16}/> Mark all read</button>}/>
 {error&&<Notice kind="error">{error}</Notice>}{query.isError&&<Notice kind="error">Could not refresh notifications. <button className="text-link inline-button" onClick={()=>void query.refetch()}>Try again</button></Notice>}
 <div className="notification-summary"><span className="round-icon blue-icon"><Bell size={18}/></span><div><strong>{query.data?.unread||0} unread updates</strong><small>Alerts are generated from your authorized attendance records.</small></div></div>
 {query.data?.items.length?<div className="notification-list">{query.data.items.map(item=><Card className={`notification-item ${item.read?'notification-read':''}`} key={item.id}><span className={`notification-icon ${item.kind==='low_attendance'?'notice-warn':''}`}>{item.kind==='low_attendance'?<TriangleAlert size={18}/>:<Info size={18}/>}</span><div className="notification-copy"><div className="notification-title-row"><h2>{item.title}</h2>{!item.read&&<Badge tone="info">New</Badge>}</div><p>{item.message}</p><small>{formatDate(item.created_at)}</small>{item.link&&<Link to={item.link} className="text-link notification-link">View related attendance <span aria-hidden>→</span></Link>}</div>{!item.read&&<button className="icon-button mark-read" title="Mark as read" onClick={()=>void mark(item.id)}><Check size={16}/></button>}</Card>)}</div>:query.isError?null:<Card><EmptyState title="You’re all caught up" message="No notifications have been generated for your account yet."/></Card>}
 <Notice kind="info">Notifications are private to your signed-in account. Low-attendance messages are calculated from recorded eligible sessions.</Notice>
 </main>;
}
