/* FanDuel sport configs — roster, cap, stacking, scoring (for display).
   Each sport: slots (key + required positions), cap, maxTeam (max players from one team),
   stack rules, scoring reference, and sport-specific UI tweaks. */
window.DFS_SPORTS = {
  mlb: {
    id:'mlb', name:'MLB', icon:'⚾', season:'Apr–Oct',
    cap:35000, maxTeam:4,
    stackUnit:'team', stackLabel:'Stack team (batters)',
    oppoOption:true, oppoLabel:'Exclude opposing pitcher',
    csvNote:'FanDuel MLB CSV: Columns include Position, Player, Salary, Team.',
    slots:[
      {key:'P',   req:['P'],  label:'P'},
      {key:'C1B', req:['C','1B','C1B'], label:'C/1B'},
      {key:'2B',  req:['2B'],  label:'2B'},
      {key:'3B',  req:['3B'],  label:'3B'},
      {key:'SS',  req:['SS'],  label:'SS'},
      {key:'OF1', req:['OF'],  label:'OF'},
      {key:'OF2', req:['OF'],  label:'OF'},
      {key:'OF3', req:['OF'],  label:'OF'},
      {key:'UTIL',req:['C','1B','C1B','2B','3B','SS','OF','UTIL'], label:'UTIL'}
    ],
    scoring:'H: 1B+3 2B+6 3B+9 HR+12 RBI+3.5 R+3.2 BB+3 HBP+3 SB+6 · P: IP+3 K+3 Win+6 ER-3 QS+4'
  },
  nfl: {
    id:'nfl', name:'NFL', icon:'🏈', season:'Sep–Feb',
    cap:60000, maxTeam:4,
    stackUnit:'team', stackLabel:'Stack team (offense)',
    oppoOption:false,
    csvNote:'FanDuel NFL CSV: Columns include Position, Player, Salary, Team, Opp.',
    slots:[
      {key:'QB',   req:['QB'],             label:'QB'},
      {key:'RB1',  req:['RB'],             label:'RB'},
      {key:'RB2',  req:['RB'],             label:'RB'},
      {key:'WR1',  req:['WR'],             label:'WR'},
      {key:'WR2',  req:['WR'],             label:'WR'},
      {key:'WR3',  req:['WR'],             label:'WR'},
      {key:'TE',   req:['TE'],             label:'TE'},
      {key:'FLEX', req:['RB','WR','TE'],   label:'FLEX'},
      {key:'DEF',  req:['DEF'],            label:'DEF'}
    ],
    scoring:'Pass: 0.04/yd, TD+4, INT-1 · Rush: 0.1/yd, TD+6 · Rec: 0.1/yd, 0.5/rec, TD+6 · Fum lost-2 · DEF: sacks+1, INT+2, TD+6'
  },
  nba: {
    id:'nba', name:'NBA', icon:'🏀', season:'Oct–Jun',
    cap:60000, maxTeam:4,
    stackUnit:'team', stackLabel:'Stack team',
    oppoOption:false,
    csvNote:'FanDuel NBA CSV: Columns include Position, Player, Salary, Team.',
    slots:[
      {key:'PG1', req:['PG'], label:'PG'},
      {key:'PG2', req:['PG'], label:'PG'},
      {key:'SG1', req:['SG'], label:'SG'},
      {key:'SG2', req:['SG'], label:'SG'},
      {key:'SF1', req:['SF'], label:'SF'},
      {key:'SF2', req:['SF'], label:'SF'},
      {key:'PF1', req:['PF'], label:'PF'},
      {key:'PF2', req:['PF'], label:'PF'},
      {key:'C',   req:['C'],  label:'C'}
    ],
    scoring:'Point+1 · Rebound+1.2 · Assist+1.5 · Steal+3 · Block+3 · Turnover-1'
  }
};
