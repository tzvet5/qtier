#include "gen/MainQuery.hpp"
#include "testframework.hpp"
#include "testutils.hpp"
#include <QSignalSpy>

namespace RootScalar {
using namespace qtgql;

auto ENV_NAME = std::string("RootScalar");
auto SCHEMA_ADDR = get_server_address(QString::fromStdString(ENV_NAME));

TEST_CASE("RootScalar") {
  auto env = test_utils::get_or_create_env(
      ENV_NAME, DebugClientSettings{.prod_settings = {.url = SCHEMA_ADDR}});
  auto mq = mainquery::MainQuery::shared();
  mq->fetch();
  test_utils::wait_for_completion(mq);
  SECTION("test deserialize") { REQUIRE(!mq->data()->get_name().isEmpty()); };
  SECTION("test update") {
    auto prev_name = mq->data()->get_name();
    auto catcher =
        test_utils::SignalCatcher({.source_obj = mq->data(), .only = "name"});
    auto mq2 = mainquery::MainQuery::shared();
    mq2->fetch();
    REQUIRE(catcher.wait());
    test_utils::wait_for_completion(mq2);
    auto new_name = mq2->data()->get_name();
    REQUIRE_NE(new_name , prev_name);
    REQUIRE_EQ(mq->data()->get_name() , new_name);
  };
}

}; // namespace RootScalar