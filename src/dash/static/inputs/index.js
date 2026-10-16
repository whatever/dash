import web, { pageInput } from "./web.js";

const hackernews = pageInput({
  kind: "hackernews",
  title: "Hacker News",
  hint: "Each new story on the page (front page, /newest, /ask, ...) becomes a memory once.",
  placeholder: "https://news.ycombinator.com/",
});

const bushwick = pageInput({
  kind: "bushwick",
  title: "Bushwick Daily",
  hint: "Each new article on the page (front page or a section) becomes a memory once.",
  placeholder: "https://bushwickdaily.com/",
});

export default [web, hackernews, bushwick];
