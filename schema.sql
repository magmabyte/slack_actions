drop table if exists actions;
create table actions (
  id integer primary key autoincrement,
  action text not null,
  user1 text not null,
  user2 text not null,
  num_action integer
);
