/** An ID lives for one attempted submission, including retries, not the page lifetime. */
export class ReviewRequestIds {
  private pending = new Map<string,string>();
  get(key:string) {
    let id=this.pending.get(key);
    if(!id){id=crypto.randomUUID();this.pending.set(key,id);}
    return id;
  }
  complete(key:string){this.pending.delete(key);}
  cancel(){this.pending.clear();}
}
